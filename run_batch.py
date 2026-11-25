from fastapi.testclient import TestClient
import growth_agent.main as gm

gm.DB_PATH = 'leads.db'
BATCH_SIZE = 35

with gm.get_db() as conn:
    cursor = conn.execute(
        "UPDATE leads SET status = 'PENDING' WHERE id IN (SELECT id FROM leads WHERE status = 'DISPATCHED_ACTIVE' LIMIT ?)",
        (BATCH_SIZE,)
    )
    conn.commit()
    print(f"Promoted {cursor.rowcount} prospects to PENDING.")

c = TestClient(gm.app)
print("Scanning attack surfaces and synthesizing pitches...")
camp_resp = c.post("/api/v1/campaign/run")
camp_data = camp_resp.json()
print(f"Processed {camp_data.get('processed_count', 0)} accounts.")

dispatched_count = 0
for item in camp_data.get("results", []):
    lid = item.get("lead_id")
    r = c.post(f"/api/v1/outreach/{lid}")
    if r.status_code == 200:
        dispatched_count += 1

print(f"Successfully dispatched {dispatched_count} live outreach emails.")
