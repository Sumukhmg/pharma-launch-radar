# Pharma Launch Radar

Finds the pharma companies most likely to buy HCP engagement and field-team AI this week, scores them, and drafts the first line of outreach.

**Why:** pharma buys HCP engagement and field tools around launches. A new FDA approval, a new indication or a label change means a spike in doctor questions and reps who need retraining. A Phase 3 readout means a launch is coming next.

## Signals (all free, no API keys)

| Signal | Source | Points |
| --- | --- | --- |
| New FDA approval (NDA/BLA, generics excluded) | [openFDA](https://open.fda.gov/apis/drug/drugsfda/) | 40 each, cap 80 |
| New indication (efficacy supplement) | openFDA | 25 each, cap 50 |
| Label change | openFDA | 10 each, cap 30 |
| Completed industry Phase 3 trial | [ClinicalTrials.gov](https://clinicaltrials.gov/data-api/api) | 10 each, cap 30 |
| Launch / medical affairs / field medical news | [GDELT](https://www.gdeltproject.org/) | 5 each, cap 15 |

**Product fit:**
- An approval or a new indication points to **Ather**, which answers HCP questions 24/7.
- A label change points to **Jarvis**, which brings field reps up to speed.
- A Phase 3 readout alone points to **Simulation Studio**, which tests messaging before launch.

## Run

```bash
python3 engine.py        # last 90 days -> signals.js (~10-15 min, GDELT news is rate-limited)
python3 test_engine.py   # self-check
open index.html
```

Python 3.9+, standard library only. A GitHub Action reruns it every Monday and commits fresh `signals.js`; Vercel redeploys on push.

## Next

- Pull job posts for medical information and MSL roles as a hiring signal.
- Push the top 10 to a CRM or Clay table each week.
- Generate the opener with an LLM instead of templates.
