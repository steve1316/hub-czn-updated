import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_machine_store_cache():
    """The machine-store miss cache is module level, so clear it between tests."""
    from api.capture import setup as capture_setup
    capture_setup._machine_store_misses.clear()
    yield
    capture_setup._machine_store_misses.clear()


@pytest.fixture(autouse=True)
def reset_optimizer_state():
    from api.state import state
    from game_data.constants import ALL_STAT_NAMES
    from optimizer import GearOptimizer
    state.optimizer = GearOptimizer()
    state.data_loaded = False
    state.loaded_file = None
    state.autoscroll_running = False
    state.capture_running = False
    state.optimizer.char_weights = {}
    state.optimizer.priorities = {name: 0 for name in ALL_STAT_NAMES}
    yield
    state.optimizer = GearOptimizer()
    state.data_loaded = False
    state.loaded_file = None
    state.autoscroll_running = False
    state.capture_running = False
    state.optimizer.char_weights = {}
    state.optimizer.priorities = {name: 0 for name in ALL_STAT_NAMES}


@pytest.fixture(autouse=True)
def isolated_capture_settings(tmp_path, monkeypatch):
    """Keep capture settings off the real snapshots folder."""
    from api.capture import settings as capture_settings
    monkeypatch.setattr(capture_settings, "SETTINGS_PATH", tmp_path / "capture_settings.json")
    from api.state import state
    state.capture_auto_started = False
    yield
    state.capture_auto_started = False
    # Auto-start tests push log lines, so leave the shared queue empty for tests that read it.
    while not state.log_queue.empty():
        state.log_queue.get_nowait()
    state.log_tail.clear()
