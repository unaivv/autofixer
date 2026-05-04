"""Entry point — run from the `ai-jira-fixer` directory with a populated `.env`."""

from orchestrator.daily_cycle import run_daily_cycle


if __name__ == "__main__":
    run_daily_cycle()
