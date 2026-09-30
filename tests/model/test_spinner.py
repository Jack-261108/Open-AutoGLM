import time
from phone_agent.model.spinner import InferenceSpinner


def test_spinner_lifecycle():
    spinner = InferenceSpinner("Testing inference")
    # Start and stop safely
    spinner.start()
    time.sleep(0.05)
    spinner.stop()
    # Idempotent stop
    spinner.stop()


def test_spinner_disabled_when_not_tty():
    spinner = InferenceSpinner("Testing inference")
    spinner._is_tty = False

    spinner.start()
    assert spinner._thread is None
    assert spinner._running is False
    spinner.stop()
