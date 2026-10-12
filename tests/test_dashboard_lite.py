import json
import sqlite3

import pytest

flask = pytest.importorskip("flask")
from dashboard_lite.app import CREDIT, create_app, load_state  # noqa: E402


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "live_account_gold.sqlite"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE trades (entry_time TEXT, exit_time TEXT, direction TEXT, entry REAL, exit REAL, stop REAL,"
                " target REAL, confidence REAL, reason TEXT, pnl REAL, R REAL, energy REAL, PRIMARY KEY (entry_time, direction))")
    con.execute("INSERT INTO trades VALUES ('2026-10-01 10:00','2026-10-01 14:00','LONG',4100,4150,4080,4160,0.7,'target',30,1.5,0.1)")
    con.execute("INSERT INTO trades VALUES ('2026-10-02 10:00','2026-10-02 12:00','SHORT',4150,4170,4170,4120,0.6,'stop',-10,-1,0.1)")
    con.execute("CREATE TABLE ticks (time TEXT PRIMARY KEY, price REAL, decision TEXT, asleep INTEGER, equity REAL, change_pct REAL, open INTEGER)")
    con.execute("INSERT INTO ticks VALUES ('2026-10-12 03:00',4190,'WAIT',0,615,0.0165,1)")
    con.execute("INSERT INTO ticks VALUES ('2026-10-12 03:01',4198,'WAIT',0,620,0.0248,1)")
    con.commit(); con.close()
    p.with_suffix(".json").write_text(json.dumps(dict(start_equity=605.0, equity=625.0,
                                      position=dict(direction=1, entry=4180.0, stop=4150.0, target=4240.0))))
    return p


def test_state(db):
    s = load_state(db)
    assert s["latest"]["price"] == 4198 and s["stats"]["n"] == 2 and s["stats"]["win_rate"] == 0.5
    assert s["stats"]["mood"] == "bull" and s["stats"]["start"] == 605.0 and s["position"]["entry"] == 4180.0


def test_pages(db):
    c = create_app(db).test_client()
    r = c.get("/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and CREDIT in html and 'dir="rtl"' in html and "<polyline" in html and "4,198.00" in html
    j = c.get("/api/state").get_json()
    assert j["stats"]["n"] == 2 and len(j["ticks"]) == 2


def test_missing_db(tmp_path):
    c = create_app(tmp_path / "nope.sqlite").test_client()
    assert c.get("/").status_code == 200 and c.get("/api/state").get_json()["exists"] is False


def test_env_db(db, monkeypatch):
    monkeypatch.setenv("GOLD_DB", str(db))
    assert create_app().config["DB"] == str(db)
