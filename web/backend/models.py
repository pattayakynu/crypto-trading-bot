"""
Re-exports engine SQLAlchemy models for use in web/backend routers.
The engine path is inserted by db.py, but since web/backend also has a db.py,
we load the engine's db module explicitly to avoid naming conflicts.
"""
import importlib.util
from pathlib import Path

_engine_db_path = Path(__file__).resolve().parent.parent.parent / "engine" / "db.py"
_spec = importlib.util.spec_from_file_location("engine_db", _engine_db_path)
_engine_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engine_db)

Trade = _engine_db.Trade
Position = _engine_db.Position
Performance = _engine_db.Performance
LayerWeight = _engine_db.LayerWeight
SignalLog = _engine_db.SignalLog
PairBlacklist = _engine_db.PairBlacklist
Base = _engine_db.Base
init_db = _engine_db.init_db
