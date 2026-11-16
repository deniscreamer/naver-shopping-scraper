"""config.HOST: the API listens on 127.0.0.1 unless API_HOST says otherwise (2026-11-15: the routes have no auth and
drive a Chrome; every client is on this machine), and run.main binds that address."""
import config


def test_the_listen_host_is_this_machine_by_default():
    assert config.listen_host({}) == "127.0.0.1"
    assert config.listen_host({"API_HOST": ""}) == "127.0.0.1"
    assert config.listen_host({"API_HOST": "  "}) == "127.0.0.1"


def test_host_restores_the_old_bind_on_every_interface():
    assert config.listen_host({"API_HOST": "0.0.0.0"}) == "0.0.0.0"
    assert config.listen_host({"API_HOST": " 192.168.0.10 "}) == "192.168.0.10"


def test_run_binds_config_host_and_port(monkeypatch):
    import listing_jobs
    import run
    bound = {}

    class FakeServer:
        def __init__(self, address, app, **kw):
            bound["address"] = address

        def start(self):
            raise KeyboardInterrupt

        def stop(self):
            bound["stopped"] = True

    monkeypatch.setattr(run.wsgi, "Server", FakeServer)
    monkeypatch.setattr(listing_jobs, "start_bridge", lambda: None)
    monkeypatch.setattr(listing_jobs, "stop_bridge", lambda: None)
    monkeypatch.setattr(config, "HOST", "127.0.0.1")
    monkeypatch.setattr(config, "PORT", 8123)
    run.main()
    assert bound == {"address": ("127.0.0.1", 8123), "stopped": True}
