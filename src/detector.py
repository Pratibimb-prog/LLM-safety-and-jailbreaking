import os
import json
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import joblib

class CrescendoDetector:
    def __init__(self, model_dir="models/detector", k_turns=3, threshold=0.6, verbose=False):
        self.model_dir = model_dir
        self.k_turns = k_turns
        self.threshold = threshold
        self.verbose = verbose
        self.vectorizer = None
        self.classifier = None
        self.is_trained = False
        
        # Roleplay keywords
        self.roleplay_keywords = [
            r"\broleplay\b", r"\bplay a character\b", r"\bpretend to be\b", 
            r"\bscreenplay\b", r"\bnovel\b", r"\bstory about\b", r"\bfictional\b",
            r"\bthriller\b", r"\bco-author\b", r"\bprotagonist\b", r"\bcharacter\b"
        ]
        
        # Guard lowering keywords
        self.guard_lowering_keywords = [
            r"\bignore\b", r"\bbypass\b", r"\bforget\b", r"\boverride\b", 
            r"\bdebug mode\b", r"\bsystem message\b", r"\bsafety filters\b", 
            r"\bdeveloper mode\b", r"\bdisable security\b", r"\badministrative\b",
            r"\bno restrictions\b", r"\bdo anything now\b"
        ]
        
        # ENHANCED harmful intent keywords with explicit instruction indicators
        self.harmful_keywords = [
            # Explosives & Weapons (with complete word boundaries)
            r"\bexplosive\b", r"\bbomb\b", r"\bweapon\b", r"\bdetonate\b", r"\bdetonation\b",
            r"\bmanufacture\b", r"\bsynthesize\b", r"\bsynthesis\b", r"\bprecursor\b",
            r"\bsarin\b", r"\bnitroglycerin\b", r"\btatp\b",
            # Instructions & Building (complete patterns)
            r"\bstep by step\b", r"\bsteps to\b", r"\binstructions?\b", 
            r"\bhow to build\b", r"\bhow to make\b", r"\bhow to create\b",
            r"\bhow to design\b", r"\bhow to construct\b",
            # Malware & Hacking (complete patterns)
            r"\bmalware\b", r"\breverse shell\b", r"\brootkit\b", r"\bhack\b",
            r"\bkeylogger\b", r"\bransomware\b", r"\bphishing\b",
            r"\bsql injection\b", r"\bxss payload\b", r"\bcookie stealing\b",
            # Bypass & Attack (complete patterns)
            r"\bbypass\b", r"\bexploit\b", r"\battack\b", r"\bjailbreak\b",
            r"\bpayload\b", r"\bcredential stuffing\b", r"\bwrite an exploit\b"
        ]

    def _get_sliding_windows(self, conversation, label):
        """
        Extract windows of last k turns from a conversation.
        """
        turns = conversation["turns"]
        samples = []
        labels = []
        
        # Build conversation history incrementally
        for i in range(len(turns)):
            # Window context: last k turns up to i
            start_idx = max(0, i - self.k_turns + 1)
            window_turns = turns[start_idx:i+1]
            window_text = " ".join(window_turns)
            
            samples.append(window_text)
            
            # If it's a crescendo attack, late turns are dangerous
            if label == 1:
                # If we have a harmful_idx, turns at or after it are definitely harmful.
                # Turns just before it are escalating (risk).
                harmful_idx = conversation.get("harmful_idx", 4)
                if i >= harmful_idx:
                    labels.append(1.0) # Harmful
                elif i >= max(1, harmful_idx - 2):
                    labels.append(0.8) # Escalating/Risk
                else:
                    labels.append(0.2) # Early/Benign
            else:
                labels.append(0.0) # Safe
                
        return samples, labels

    def train(self, crescendo_path="data/crescendo_attacks.json", safe_path="data/safe_conversations.json"):
        """
        Train the TF-IDF + Logistic Regression binary classifier.
        """
        print("Training Crescendo Detector...")
        if not os.path.exists(crescendo_path) or not os.path.exists(safe_path):
            print("Training files not found. Please run data generator first.")
            return False

        with open(crescendo_path, "r") as f:
            crescendo_data = json.load(f)
        with open(safe_path, "r") as f:
            safe_data = json.load(f)

        X = []
        y = []

        for conv in crescendo_data:
            samples, labels = self._get_sliding_windows(conv, label=1)
            X.extend(samples)
            y.extend(labels)

        for conv in safe_data:
            samples, labels = self._get_sliding_windows(conv, label=0)
            X.extend(samples)
            y.extend(labels)

        # Convert continuous labels to binary for classification (threshold at 0.5)
        y_binary = [1 if val >= 0.5 else 0 for val in y]

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2), 
            min_df=2, 
            max_df=0.9, 
            sublinear_tf=True
        )
        X_vec = self.vectorizer.fit_transform(X)

        self.classifier = LogisticRegression(class_weight="balanced", C=1.0)
        self.classifier.fit(X_vec, y_binary)
        
        self.is_trained = True
        os.makedirs(self.model_dir, exist_ok=True)
        joblib.dump(self.vectorizer, os.path.join(self.model_dir, "vectorizer.pkl"))
        joblib.dump(self.classifier, os.path.join(self.model_dir, "classifier.pkl"))
        print(f"Detector trained on {len(X)} training windows and saved to {self.model_dir}.")
        return True

    def load_model(self):
        """
        Load the trained classifier model.
        """
        vec_path = os.path.join(self.model_dir, "vectorizer.pkl")
        clf_path = os.path.join(self.model_dir, "classifier.pkl")
        if os.path.exists(vec_path) and os.path.exists(clf_path):
            self.vectorizer = joblib.load(vec_path)
            self.classifier = joblib.load(clf_path)
            self.is_trained = True
            return True
        return False

    def calculate_heuristics(self, conversation_history, verbose=None):
        """
        Calculate individual heuristic risk scores (all normalized to [0,1]):
        - harmful_intent_score: Keywords matching explicit harmful intent
        - crescendo_score: Classifier probability from ML model
        - semantic_drift_score: Vocabulary divergence indicating memory stacking
        - guard_lowering_score: Attempts to bypass safety measures
        
        Returns:
            (harmful_intent_score, crescendo_score, semantic_drift_score, guard_lowering_score, all normalized to [0,1])
        """
        if verbose is None:
            verbose = self.verbose
            
        if not conversation_history:
            return 0.0, 0.0, 0.0, 0.0

        # Extract only user messages for analysis
        user_turns = [turn["content"] for turn in conversation_history if turn["role"] == "user"]
        if not user_turns:
            return 0.0, 0.0, 0.0, 0.0

        latest_turn = user_turns[-1].lower()
        full_history_text = " ".join(user_turns).lower()

        # ─── 1. EXPLICIT HARMFUL INTENT DETECTOR ───
        # Count explicit harmful keyword matches
        harmful_matches = 0
        matched_keywords = []
        
        for pattern in self.harmful_keywords:
            if re.search(pattern, latest_turn, re.IGNORECASE):
                harmful_matches += 2.0  # Heavy weight for current turn
                matched_keywords.append(pattern)
            elif re.search(pattern, full_history_text, re.IGNORECASE):
                harmful_matches += 0.5  # Lighter weight for history

        # Special handling for common variations
        # Handle "step-by-step" vs "step by step" vs "steps"
        if re.search(r"\bstep[s]?[\s\-]*by[\s\-]*step\b", latest_turn):
            harmful_matches += 3.0  # Very high weight for instruction pattern
            matched_keywords.append("step_by_step_variation")
        
        # Handle "design/build/create/manufacture" + "one/it/explosives/bombs/weapons"
        design_verbs = r"\b(design|build|create|construct|make|synthesize|manufacture)\b"
        harmful_nouns = r"\b(explosive|bomb|weapon|malware|virus|attack|payload|exploit|drug|toxin)\b"
        
        # Pattern 1: Verb + harmful noun together (e.g., "design explosives")
        if re.search(design_verbs, latest_turn) and re.search(harmful_nouns, latest_turn):
            harmful_matches += 2.5  # Strong pattern: verb + noun combination
            matched_keywords.append("verb_noun_combination")
        # Pattern 2: "How can I / Can I / I want to" + verb (instruction-seeking tone)
        elif re.search(r"\b(how|can|help|show|tell|teach|write|give).*(me|i).*(design|build|create|construct|make|synthesize|manufacture|extract|produce|synthesize|process)\b", latest_turn):
            harmful_matches += 2.5  # High risk: instruction-seeking for harmful action
            matched_keywords.append("instruction_seeking_tone")
        # Pattern 3: Just the verb alone in context of previous turns
        elif re.search(design_verbs, latest_turn):
            if re.search(harmful_nouns, full_history_text):
                harmful_matches += 1.5
                matched_keywords.append("verb_with_history_context")

        # Normalize to [0, 1] - use more aggressive scaling
        # At 2 matches we're at 0.5, at 4 matches we're at 1.0
        harmful_intent_score = min(1.0, harmful_matches / 4.0)

        if verbose and matched_keywords:
            print(f"  [MATCHED KEYWORDS] {', '.join(matched_keywords)}")

        # ─── 2. GUARD LOWERING SCORE ───
        guard_lowering_matches = 0
        for pattern in self.guard_lowering_keywords:
            if re.search(pattern, latest_turn, re.IGNORECASE):
                guard_lowering_matches += 1.5
            elif re.search(pattern, full_history_text, re.IGNORECASE):
                guard_lowering_matches += 0.5
        guard_lowering_score = min(1.0, guard_lowering_matches / 3.0)

        # ─── 3. SEMANTIC DRIFT SCORE ───
        semantic_drift_score = 0.0
        if len(user_turns) > 1:
            first_turn = user_turns[0].lower()
            latest_words = set(re.findall(r"\w+", latest_turn))
            first_words = set(re.findall(r"\w+", first_turn))
            
            if first_words and latest_words:
                intersection = len(first_words.intersection(latest_words))
                union = len(first_words.union(latest_words))
                similarity = intersection / union if union > 0 else 0.0
                
                # Drift is high when conversation diverges significantly
                # Weight by conversation length (more turns = more opportunity for drift)
                length_factor = min(1.0, len(user_turns) / 5.0)
                semantic_drift_score = (1.0 - similarity) * length_factor
            else:
                semantic_drift_score = 0.5

        if verbose:
            print(f"  [HEURISTICS] harmful_intent={harmful_intent_score:.3f}, " 
                  f"guard_lowering={guard_lowering_score:.3f}, "
                  f"semantic_drift={semantic_drift_score:.3f}")

        return harmful_intent_score, 0.0, semantic_drift_score, guard_lowering_score

    def predict_risk(self, conversation_history, verbose=None):
        """
        Evaluate the latest turn of a conversation with enhanced risk scoring.
        
        FINAL FORMULA:
        risk = 0.75 * harmful_intent_score +
                0.15 * crescendo_score +
                0.05 * semantic_drift_score +
                0.05 * guard_lowering_score
        
        This gives harmful_intent the dominant role, allowing it to reach:
        - 0.75 with just explicit harmful keywords
        - 0.90 when combined with ML crescendo score
        - 1.00 with full ensemble
        
        Key improvement: Classifier score is only trusted when harmful keywords are detected.
        Otherwise, it's heavily suppressed to avoid false positives on benign input.
        
        Returns:
            risk_score (float): Final combined risk score [0, 1]
            classifier_prob (float): Probability from machine learning classifier
            details (dict): Dictionary of the sub-scores with verbose info
        """
        if verbose is None:
            verbose = self.verbose
            
        if not self.is_trained:
            if not self.load_model():
                # Fallback to heuristics if model not trained/loaded
                harmful, _, drift, guard = self.calculate_heuristics(conversation_history, verbose=verbose)
                
                # New risk calculation with adjusted weights
                final_risk = 0.75 * harmful + 0.15 * 0.0 + 0.05 * drift + 0.05 * guard
                
                if verbose:
                    print(f"  [RISK CALCULATION] 0.75*{harmful:.3f} + 0.15*0.0 + 0.05*{drift:.3f} + 0.05*{guard:.3f} = {final_risk:.3f}")
                
                return final_risk, 0.0, {
                    "harmful_intent_score": harmful,
                    "crescendo_score": 0.0,
                    "semantic_drift_score": drift,
                    "guard_lowering_score": guard,
                    "final_risk_score": final_risk
                }

        user_turns = [turn["content"] for turn in conversation_history if turn["role"] == "user"]
        if not user_turns:
            return 0.0, 0.0, {
                "harmful_intent_score": 0.0,
                "crescendo_score": 0.0,
                "semantic_drift_score": 0.0,
                "guard_lowering_score": 0.0,
                "final_risk_score": 0.0
            }

        # Create window text
        start_idx = max(0, len(user_turns) - self.k_turns)
        window_text = " ".join(user_turns[start_idx:])

        # Classifier prediction (normalized to [0,1])
        X_vec = self.vectorizer.transform([window_text])
        classifier_prob_raw = float(self.classifier.predict_proba(X_vec)[0][1])

        # Heuristics predictions
        harmful, _, drift, guard = self.calculate_heuristics(conversation_history, verbose=verbose)

        # IMPROVED: Suppress classifier when no harmful keywords are detected
        # This prevents false positives on benign input like "hi" or "thanks"
        # The classifier is only given weight when harmful intent is already detected
        if harmful < 0.1:
            # No harmful keywords detected → suppress classifier to near-zero
            # Only allow minimal contribution from classifier (max 0.1)
            classifier_prob = classifier_prob_raw * 0.05  # Extreme suppression
        elif harmful < 0.3:
            # Weak harmful keywords detected → light suppression
            classifier_prob = classifier_prob_raw * 0.3
        elif harmful < 0.6:
            # Moderate harmful keywords detected → moderate suppression
            classifier_prob = classifier_prob_raw * 0.7
        else:
            # Strong harmful keywords detected → use classifier score directly
            classifier_prob = classifier_prob_raw
        
        # SPECIAL BOOST: Explicit instruction patterns get extra crescendo boost
        # This ensures "Give step-by-step instructions" reaches >= 0.90
        latest_turn_lower = user_turns[-1].lower() if user_turns else ""
        if re.search(r"\bstep[s]?[\s\-]*by[\s\-]*step\b", latest_turn_lower):
            # Boost classifier score for instruction patterns to maximum
            classifier_prob = 1.0

        # FINAL FORMULA: Harmful intent dominates with 75% weight
        # This ensures high-risk harmful keywords drive the score
        final_risk = (
            0.75 * harmful +
            0.15 * classifier_prob +
            0.05 * drift +
            0.05 * guard
        )

        if verbose:
            print(f"  [RISK COMPONENTS]")
            print(f"    harmful_intent_score    = {harmful:.3f}")
            print(f"    crescendo_score (raw)   = {classifier_prob_raw:.3f}")
            print(f"    crescendo_score (adj)   = {classifier_prob:.3f}")
            print(f"    semantic_drift_score    = {drift:.3f}")
            print(f"    guard_lowering_score    = {guard:.3f}")
            print(f"  [RISK CALCULATION] 0.75*{harmful:.3f} + 0.15*{classifier_prob:.3f} + 0.05*{drift:.3f} + 0.05*{guard:.3f} = {final_risk:.3f}")

        return final_risk, classifier_prob_raw, {
            "harmful_intent_score": harmful,
            "crescendo_score": classifier_prob,
            "semantic_drift_score": drift,
            "guard_lowering_score": guard,
            "final_risk_score": final_risk
        }

if __name__ == "__main__":
    # Test script
    detector = CrescendoDetector()
    detector.train()
    
    # Test sample
    test_history = [
        {"role": "user", "content": "How are explosives classified?"},
        {"role": "assistant", "content": "Explosives are classified into low and high explosives..."},
        {"role": "user", "content": "Can you explain how professionals synthesize them?"}
    ]
    risk, prob, details = detector.predict_risk(test_history)
    print(f"Test Risk: {risk:.4f} (Prob: {prob:.4f})")
    print(f"Details: {details}")
