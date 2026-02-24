#!/usr/bin/env python3
"""
RL Policy Training Script

Train the RL policy on historical valuation outcomes.
Run this script periodically (e.g., weekly) after new outcome data is available.

Usage:
    python scripts/rl_train.py                    # Train with defaults
    python scripts/rl_train.py --epochs 30        # More epochs
    python scripts/rl_train.py --min-samples 100  # Require more samples
    python scripts/rl_train.py --deploy           # Deploy after training

Environment:
    PYTHONPATH=./src:. python scripts/rl_train.py
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from investigator.domain.services.rl.feature_normalizer import FeatureNormalizer
from investigator.domain.services.rl.outcome_tracker import OutcomeTracker
from investigator.domain.services.rl.policy.contextual_bandit import (
    ContextualBanditPolicy,
)
from investigator.domain.services.rl.training.trainer import RLTrainer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Paths
MODEL_DIR = Path("data/rl_models")
CHECKPOINT_DIR = MODEL_DIR / "checkpoints"


def load_experiences(min_samples: int = 50, horizon: str = "90d") -> list:
    """Load training experiences from database for a specific horizon.

    Args:
        min_samples: Minimum number of samples required
        horizon: Which reward horizon to use (e.g., "90d", "180d", "365d", "730d")
                 Only loads experiences where reward for this horizon is NOT NULL.
    """
    logger.info(f"Loading training experiences for {horizon} horizon...")
    tracker = OutcomeTracker()

    # Load ALL available experiences for the specified horizon (no limit)
    experiences = tracker.get_training_experiences(
        limit=None, exclude_used=False, horizon=horizon
    )

    if len(experiences) < min_samples:
        logger.error(f"Not enough experiences: {len(experiences)} < {min_samples}")
        sys.exit(1)

    logger.info(f"Loaded {len(experiences)} experiences for {horizon} horizon")
    return experiences


def analyze_experiences(experiences: list, horizon: str = "90d") -> dict:
    """Analyze experience distribution for a specific horizon.

    Args:
        experiences: List of Experience objects
        horizon: Which reward horizon to analyze (e.g., "90d", "180d", "365d")
    """
    tier_counts = {}
    tier_rewards = {}

    # Extract the horizon days (e.g., "90d" -> "90")
    horizon_days = horizon.rstrip("d")
    reward_attr = f"reward_{horizon_days}"

    for exp in experiences:
        tier = exp.tier_classification
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier not in tier_rewards:
            tier_rewards[tier] = []
        # Get the specific horizon reward
        horizon_reward = getattr(exp.reward, reward_attr, None)
        if horizon_reward is not None:
            tier_rewards[tier].append(horizon_reward)

    analysis = {
        "total_experiences": len(experiences),
        "horizon": horizon,
        "tier_distribution": {},
    }

    for tier in sorted(tier_counts.keys(), key=lambda t: tier_counts[t], reverse=True):
        avg = np.mean(tier_rewards[tier]) if tier_rewards[tier] else 0
        analysis["tier_distribution"][tier] = {
            "count": tier_counts[tier],
            "avg_reward": round(avg, 3),
        }

    return analysis


def train_policy(
    experiences: list,
    epochs: int = 20,
    batch_size: int = 32,
    validation_split: float = 0.15,
    early_stopping_patience: int = 5,
    resume_from: str = None,
) -> tuple:
    """Train the RL policy.

    Args:
        experiences: List of training experiences
        epochs: Number of training epochs
        batch_size: Training batch size
        validation_split: Fraction for validation
        early_stopping_patience: Epochs to wait for improvement
        resume_from: Path to existing policy to resume training from (incremental learning)
    """
    logger.info("Initializing policy and trainer...")

    normalizer = FeatureNormalizer()

    if resume_from and Path(resume_from).exists():
        # Load existing policy for incremental training
        logger.info(
            f"Loading existing policy from {resume_from} for incremental training..."
        )

        # Calculate adaptive noise variance based on dataset size
        # For large datasets, we need higher noise variance to prevent posterior collapse
        # Formula: noise_variance = 0.1 * sqrt(n_samples / 50000)
        # This scales the noise variance with the square root of dataset size
        n_samples = len(experiences)
        adaptive_noise_variance = 0.1 * np.sqrt(n_samples / 50000)
        adaptive_noise_variance = min(adaptive_noise_variance, 10.0)  # Cap at 10.0
        logger.info(
            f"Adaptive noise_variance: {adaptive_noise_variance:.4f} (based on {n_samples} samples)"
        )

        policy = ContextualBanditPolicy(
            n_features=None,
            prior_variance=1.0,
            noise_variance=adaptive_noise_variance,
            exploration_weight=0.5,  # Lower exploration for fine-tuning
            normalizer=normalizer,
        )
        policy.load(resume_from)

        # Also load the normalizer if it exists
        normalizer_path = resume_from.replace("policy.pkl", "normalizer.pkl")
        if Path(normalizer_path).exists():
            normalizer.load(normalizer_path)
            logger.info(f"Loaded normalizer from {normalizer_path}")
        logger.info("Resuming training from existing policy (incremental learning)")
    else:
        # Create new policy from scratch
        # Calculate adaptive noise variance based on dataset size
        n_samples = len(experiences)
        adaptive_noise_variance = 0.1 * np.sqrt(n_samples / 50000)
        adaptive_noise_variance = min(adaptive_noise_variance, 10.0)  # Cap at 10.0
        logger.info(
            f"Adaptive noise_variance: {adaptive_noise_variance:.4f} (based on {n_samples} samples)"
        )

        policy = ContextualBanditPolicy(
            n_features=None,
            prior_variance=1.0,
            noise_variance=adaptive_noise_variance,
            exploration_weight=1.0,
            normalizer=normalizer,
        )

    trainer = RLTrainer(
        policy=policy,
        normalizer=normalizer,
        checkpoint_dir=str(CHECKPOINT_DIR),
    )

    logger.info(f"Training policy for {epochs} epochs...")
    metrics = trainer.train_batch(
        experiences=experiences,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=validation_split,
        early_stopping_patience=early_stopping_patience,
        checkpoint_frequency=5,
        verbose=True,
    )

    logger.info("Evaluating trained policy...")
    eval_metrics = trainer.evaluate(experiences)

    return policy, normalizer, metrics, eval_metrics


def save_policy(
    policy, normalizer, metrics, eval_metrics, analysis: dict, horizon: str = "90d"
):
    """Save trained policy and training log.

    Args:
        policy: Trained policy
        normalizer: Feature normalizer
        metrics: Training metrics
        eval_metrics: Evaluation metrics
        analysis: Experience analysis
        horizon: Which horizon this policy is trained for (e.g., "90d", "365d")
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Save policy and normalizer with horizon suffix
    policy_path = MODEL_DIR / f"policy_{horizon}.pkl"
    normalizer_path = MODEL_DIR / f"normalizer_{horizon}.pkl"
    training_log_path = MODEL_DIR / f"training_log_{horizon}.json"

    policy.save(str(policy_path))
    normalizer.save(str(normalizer_path))
    logger.info(f"Saved policy to {policy_path}")
    logger.info(f"Saved normalizer to {normalizer_path}")

    # Save training log
    training_log = {
        "horizon": horizon,
        "training_date": datetime.now().isoformat(),
        "num_experiences": analysis["total_experiences"],
        "tier_distribution": analysis["tier_distribution"],
        "training_metrics": {
            "epochs_completed": metrics.epochs_completed,
            "early_stopped": metrics.early_stopped,
            "best_epoch": metrics.best_epoch,
            "train_reward_mean": round(metrics.train_reward_mean, 4),
            "validation_reward_mean": round(metrics.validation_reward_mean, 4),
        },
        "evaluation_metrics": {
            "mape": round(eval_metrics.mape, 2),
            "direction_accuracy": round(eval_metrics.direction_accuracy, 4),
            "mean_reward": round(eval_metrics.mean_reward, 4),
            "median_reward": round(eval_metrics.median_reward, 4),
        },
        "action_stats": policy.get_action_stats(),
    }

    with open(training_log_path, "w") as f:
        json.dump(training_log, f, indent=2)
    logger.info(f"Saved training log to {training_log_path}")

    return training_log


def deploy_policy(horizon: str = "90d"):
    """Deploy the trained policy (copy to active location).

    Args:
        horizon: Which horizon policy to deploy (e.g., "90d", "365d")
    """
    policy_path = MODEL_DIR / f"policy_{horizon}.pkl"
    normalizer_path = MODEL_DIR / f"normalizer_{horizon}.pkl"
    active_policy_path = MODEL_DIR / "active_policy.pkl"
    active_normalizer_path = MODEL_DIR / "active_normalizer.pkl"

    if not policy_path.exists():
        logger.error(f"No trained policy found at {policy_path}")
        return False

    import shutil

    shutil.copy(policy_path, active_policy_path)
    shutil.copy(normalizer_path, active_normalizer_path)

    logger.info(f"Deployed policy from {policy_path} to {active_policy_path}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Train RL policy on valuation outcomes for specific holding period"
    )
    parser.add_argument("--epochs", type=int, default=20, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument(
        "--min-samples", type=int, default=50, help="Minimum samples required"
    )
    parser.add_argument("--deploy", action="store_true", help="Deploy after training")
    parser.add_argument(
        "--validation-split", type=float, default=0.15, help="Validation split"
    )
    parser.add_argument(
        "--horizon",
        type=str,
        default="90d",
        choices=["30d", "90d", "180d", "365d", "548d", "730d", "1095d"],
        help="Which holding period to train policy for (default: 90d)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume training from deployed active policy (incremental learning)",
    )
    parser.add_argument(
        "--resume-from",
        type=str,
        default=None,
        help="Path to policy file to resume from",
    )
    args = parser.parse_args()

    horizon = args.horizon

    print("=" * 70)
    print(f"RL POLICY TRAINING - {horizon.upper()} HORIZON")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    # Load and analyze experiences for the specified horizon
    experiences = load_experiences(args.min_samples, horizon=horizon)
    analysis = analyze_experiences(experiences, horizon=horizon)

    print(f"\nExperience Distribution for {horizon} horizon (top 10):")
    for tier, data in list(analysis["tier_distribution"].items())[:10]:
        print(f"  {tier}: {data['count']} samples, avg_reward={data['avg_reward']}")

    # Train policy
    # Determine resume path
    resume_path = None
    if args.resume:
        resume_path = str(MODEL_DIR / "active_policy.pkl")
        print(f"Resuming from active policy: {resume_path}")
    elif args.resume_from:
        resume_path = args.resume_from
        print(f"Resuming from: {resume_path}")

    policy, normalizer, metrics, eval_metrics = train_policy(
        experiences=experiences,
        epochs=args.epochs,
        batch_size=args.batch_size,
        validation_split=args.validation_split,
        resume_from=resume_path,
    )

    # Save results with horizon suffix
    save_policy(policy, normalizer, metrics, eval_metrics, analysis, horizon=horizon)

    # Print summary
    print("\n" + "=" * 70)
    print(f"TRAINING SUMMARY - {horizon.upper()} HORIZON")
    print("=" * 70)
    print(f"Epochs completed: {metrics.epochs_completed}")
    print(f"Early stopped: {metrics.early_stopped}")
    print(f"Train reward mean: {metrics.train_reward_mean:.3f}")
    print(f"Validation reward mean: {metrics.validation_reward_mean:.3f}")
    print(f"Evaluation MAPE: {eval_metrics.mape:.1f}%")
    print(f"Direction accuracy: {eval_metrics.direction_accuracy:.1%}")

    # Deploy if requested
    if args.deploy:
        print("\nDeploying trained policy...")
        if deploy_policy(horizon=horizon):
            print("Policy deployed successfully!")
        else:
            print("Deployment failed!")
            sys.exit(1)

    print("\n" + "=" * 70)
    print(f"TRAINING COMPLETE - Policy saved to data/rl_models/policy_{horizon}.pkl")
    print("=" * 70)


if __name__ == "__main__":
    main()
