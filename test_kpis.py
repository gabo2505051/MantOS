import sys
import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
db = sqlite3.connect(str(_ROOT / "data" / "mantos.db"))

print("Count of PM01 for LA2:", db.execute("SELECT COUNT(*) FROM maintenance_orders JOIN equipment USING (equnr) WHERE linea='LA2' AND auart='PM01'").fetchone()[0])
print("Count of PM01 with duration > 0 for LA2:", db.execute("SELECT COUNT(*) FROM maintenance_orders JOIN equipment USING (equnr) WHERE linea='LA2' AND auart='PM01' AND duration_min > 0").fetchone()[0])
print("Count of ghost stops for LA2:", db.execute("SELECT COUNT(*) FROM maintenance_orders JOIN equipment USING (equnr) WHERE linea='LA2' AND is_ghost_stop=1").fetchone()[0])
print("Distinct auarts for LA2:", db.execute("SELECT DISTINCT auart FROM maintenance_orders JOIN equipment USING (equnr) WHERE linea='LA2'").fetchall())

