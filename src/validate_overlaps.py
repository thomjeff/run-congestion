import pandas as pd

# edit these start times if they change
start_times = {"Full": 420, "10K": 440, "Half": 460}

ov = pd.read_csv("overlaps.csv")  # normalized file
ov.columns = [c.strip().lower() for c in ov.columns]

# Expect columns: event, start, end, overlapswith
assert {"event", "start", "end", "overlapswith"}.issubset(set(ov.columns))

# Normalize names
ov["event"] = ov["event"].str.strip()
ov["overlapswith"] = ov["overlapswith"].str.strip()

# 1. Direction sanity: event must start earlier than overlapswith
bad_direction = []
for _, row in ov.iterrows():
    prev = row["event"]
    curr = row["overlapswith"]
    if start_times.get(prev, 0) >= start_times.get(curr, 1e9):
        bad_direction.append((prev, curr, row["start"], row["end"]))

if bad_direction:
    print("❗ Overlap rows with incorrect direction (should be earlier → later):")
    for b in bad_direction:
        print(" ", b)
else:
    print("✅ All overlap rows correctly directed.")

# 2. Duplicate segments
dups = ov.duplicated(subset=["event", "start", "end", "overlapswith"], keep=False)
if dups.any():
    print("⚠️ Duplicate overlap rows found:")
    print(ov[dups])
else:
    print("✅ No exact duplicate rows.")

# 3. Optional: if you have legacy entries in a file, load and canonicalize them here for diffing.