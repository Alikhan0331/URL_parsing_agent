"""CLI-обёртка для разового ручного/крон-запуска суточного обхода."""
from event_agent.pipeline.runner import run_daily
from event_agent.utils.logging import setup_logging

if __name__ == "__main__":
    setup_logging()
    run_daily()
