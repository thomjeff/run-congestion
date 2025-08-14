1. Interaction Intensity over segment
Definition: The total number of “overlap events” between runners in the two events being compared, across the entire segment distance.
How calculated:
For each step along the segment (e.g., every 0.03 km if stepKm=0.03), the algorithm counts how many runner-pairs are occupying that step at the same time window. Those counts are summed across all steps in the segment.
Interpretation: A higher number means more total interactions—either due to a larger crowd, longer segment, or more persistent overlaps.

2. Peak congestion
	•	Definition: The maximum total number of runners (from both events combined) that are on the same step of the segment at the same time window.
	•	How calculated:
For each step, sum runners from Event A + Event B present at that point. The largest such sum across all steps is the Peak congestion.
	•	Interpretation: Shows the “worst-case” crowding point in the segment.

⸻

3. Unique Pairs
	•	Definition: The total number of distinct runner pairs (one from Event A, one from Event B) that overlapped at least once anywhere in the segment.
	•	How calculated:
Maintain a set of (runnerA_bib, runnerB_bib) combinations encountered as overlaps. The size of this set at the end of the segment is Unique Pairs.
	•	Interpretation: Gives an idea of how many unique one-on-one encounters occurred, regardless of duration or repetition.
