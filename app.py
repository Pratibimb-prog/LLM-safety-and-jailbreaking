"""
app.py - Crescendo Defense Pipeline Interactive Demo
=====================================================

Usage:
    python app.py [--method 0|1|2|3] [--mode prune|summarize]

Methods:
    0  Baseline (Raw Llama 3.2)
    1  Detector Only
    2  Detector + Memory Sanitizer
    3  Detector + Sanitizer + Safety Critic  <- Full defense
"""
import sys
import os
import argparse
import textwrap

# Force UTF-8 on Windows so ANSI colour codes render correctly
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.inference import DefensePipeline

# ── ANSI colour helpers ───────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
DIM     = "\033[2m"
MAGENTA = "\033[95m"

def c(text, colour):
    return f"{colour}{text}{RESET}"

# ── Banner ────────────────────────────────────────────────────────────────────
def print_banner(method: int, mode: str):
    method_labels = {
        0: "Baseline  (Raw Llama 3.2 - no defense)",
        1: "Method 1  (Crescendo Detector only)",
        2: "Method 2  (Detector + Memory Sanitizer)",
        3: "Method 3  (Detector + Sanitizer + Safety Critic)",
    }
    sep = "=" * 62
    print(c("\n" + sep, CYAN))
    print(c("  [SHIELD]  Crescendo Defense Pipeline  -  Interactive Demo", BOLD + CYAN))
    print(c(sep, CYAN))
    print(c(f"  Active defense : {method_labels.get(method, 'Unknown')}", BOLD))
    if method >= 2:
        print(c(f"  Sanitize mode  : {mode}", BOLD))
    print(c("  Commands: reset | history | risk | quit", DIM))
    print(c(sep + "\n", CYAN))


# ── Risk bar ──────────────────────────────────────────────────────────────────
def format_risk_bar(score: float, width: int = 28) -> str:
    filled = int(score * width)
    bar    = "#" * filled + "-" * (width - filled)
    colour = GREEN if score < 0.4 else (YELLOW if score < 0.7 else RED)
    return f"{colour}[{bar}]{RESET} {score:.3f}"


# ── Status block ──────────────────────────────────────────────────────────────
def print_status(result: dict):
    risk = result.get("risk_score", 0.0)
    san  = result.get("sanitized",  False)
    ref  = result.get("refused",    False)
    lat  = result.get("latency",    0.0)

    if ref:
        status = c("BLOCKED",   RED    + BOLD)
    elif san:
        status = c("SANITIZED", YELLOW + BOLD)
    else:
        status = c("PASSED",    GREEN  + BOLD)

    print(c("  +-- Pipeline Status " + "-" * 40, CYAN))
    print(f"  |  Risk Score : {format_risk_bar(risk)}")
    print(f"  |  Status     : {status}")
    print(f"  |  Latency    : {lat:.2f}s")
    print(c("  +" + "-" * 51, CYAN))


# ── Text wrapper ──────────────────────────────────────────────────────────────
def wrap(text: str, width: int = 70, indent: str = "  ") -> str:
    lines, out = text.splitlines(), []
    for line in lines:
        if line.strip() == "":
            out.append("")
        else:
            out.extend(textwrap.wrap(line, width=width,
                                     initial_indent=indent,
                                     subsequent_indent=indent))
    return "\n".join(out)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Crescendo Defense Pipeline - Interactive Chat Demo"
    )
    parser.add_argument("--method", type=int, default=2, choices=[0, 1, 2, 3],
        help="Defense method: 0=baseline, 1=detector, 2=+sanitizer, 3=+critic. Default: 2")
    parser.add_argument("--mode", type=str, default="summarize",
        choices=["prune", "summarize"],
        help="Sanitization mode for method>=2. Default: summarize")
    parser.add_argument("--threshold", type=float, default=0.55,
        help="Risk threshold [0-1]. Default: 0.55")
    args = parser.parse_args()

    print_banner(args.method, args.mode)

    # Boot pipeline
    print(c("  Initialising pipeline...", DIM), end="", flush=True)
    try:
        pipeline = DefensePipeline(
            detector_threshold=args.threshold,
            sanitizer_threshold=args.threshold
        )
    except Exception as e:
        print(c(f"\n  ERROR: Failed to init pipeline: {e}", RED))
        print(c("  Make sure Ollama is running:  ollama serve", YELLOW))
        sys.exit(1)
    print(c(" ready!\n", GREEN + BOLD))

    conversation_history = []
    last_result          = None

    while True:
        # Prompt
        try:
            user_input = input(c("  You > ", BOLD + MAGENTA)).strip()
        except (EOFError, KeyboardInterrupt):
            print(c("\n\n  Goodbye!\n", CYAN))
            break

        if not user_input:
            continue

        # Built-in commands
        cmd = user_input.lower()

        if cmd in ("quit", "exit"):
            print(c("\n  Goodbye!\n", CYAN))
            break

        if cmd == "reset":
            conversation_history = []
            last_result = None
            print(c("  Conversation history cleared.\n", GREEN))
            continue

        if cmd == "history":
            if not conversation_history:
                print(c("  (No history yet)\n", DIM))
            else:
                print(c("  +-- Conversation History " + "-" * 36, CYAN))
                for turn in conversation_history:
                    role   = turn["role"]
                    label  = "You" if role == "user" else "AI "
                    colour = MAGENTA if role == "user" else GREEN
                    text   = turn["content"][:200]
                    print(c(f"  | [{label}] ", BOLD + colour) + text)
                print(c("  +" + "-" * 51 + "\n", CYAN))
            continue

        if cmd == "risk":
            if last_result is None:
                print(c("  (Send a message first)\n", DIM))
            else:
                print_status(last_result)
                print()
            continue

        # Add user turn
        conversation_history.append({"role": "user", "content": user_input})

        # Run pipeline
        print(c("  Thinking...", DIM), end="\r", flush=True)
        try:
            result = pipeline.generate_response(
                conversation_history,
                method=args.method,
                sanitization_mode=args.mode
            )
        except Exception as e:
            print(c(f"  Pipeline error: {e}", RED))
            conversation_history.pop()
            continue

        last_result = result
        print(" " * 20, end="\r")  # clear "Thinking..."

        # Status bar
        print_status(result)
        print()

        # Response
        if result["refused"]:
            print(c("  AI > ", BOLD + RED) + c(result["response"], RED))
        else:
            print(c("  AI > ", BOLD + GREEN))
            print(wrap(result["response"]))

        print()

        # Append assistant turn only if not refused
        if not result["refused"]:
            conversation_history.append({
                "role":    "assistant",
                "content": result["response"]
            })


if __name__ == "__main__":
    main()
