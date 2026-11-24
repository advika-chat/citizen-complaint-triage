"""Idempotent demo data: 15 synthetic complaints around downtown Austin, TX.

No LLM call is made unless --embed is passed (and a key is configured).
"""
import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from database import SessionLocal
from models import Category as C, Complaint, ComplaintNote, Status as S, Urgency as U

# (text, category, urgency, summary, department, status, lat, lng)
ROWS = [
    ("The streetlight outside 412 Congress Ave has been off for over a week and the block is very dark at night.",
     C.streetlight, U.medium, "Streetlight out on Congress Ave for a week.", "Public Works - Street Lighting", S.open, 30.2672, -97.7431),
    ("Broken streetlight on Congress near 4th street, totally dark at night, been like this for days.",
     C.streetlight, U.medium, "Streetlight dark near Congress and 4th.", "Public Works - Street Lighting", S.open, 30.2678, -97.7433),
    ("Exposed live wiring hanging from a lamp post on Red River Street, kids walk past it to school.",
     C.energy, U.high, "Exposed live wiring on Red River lamp post.", "Austin Energy - Emergency Response", S.in_progress, 30.2689, -97.7360),
    ("Sewage is bubbling up from the manhole on E 6th St and the smell is unbearable.",
     C.water, U.high, "Sewage overflowing from E 6th St manhole.", "Water Utility - Wastewater", S.in_progress, 30.2680, -97.7385),
    ("There is a strong chemical smell near the old warehouse on Waller Creek, people are getting headaches.",
     C.pollution, U.high, "Strong chemical smell near Waller Creek warehouse.", "Environmental Health", S.open, 30.2715, -97.7370),
    ("Someone is burning trash in the empty lot behind Rainey Street, thick black smoke is drifting over homes.",
     C.pollution, U.high, "Illegal trash burning on Rainey Street lot.", "Fire Department - Code Enforcement", S.resolved, 30.2570, -97.7385),
    ("Huge crowd squeezing through the narrow Sixth Street exit after the concert, people are getting crushed.",
     C.crowd_monitoring, U.high, "Dangerous crowd crush at Sixth Street exit.", "Public Safety - Event Management", S.resolved, 30.2672, -97.7410),
    ("Water main seems to be leaking on Lavaca, the water is running down the road all day.",
     C.water, U.medium, "Water main leaking on Lavaca Street.", "Water Utility", S.open, 30.2700, -97.7440),
    ("Garbage was not collected on our block of W 5th this week and the bins are overflowing.",
     C.waste, U.medium, "Missed garbage collection on W 5th.", "Solid Waste Services", S.open, 30.2660, -97.7500),
    ("Power has been out in our apartment building on Guadalupe since this morning.",
     C.energy, U.medium, "Power outage in Guadalupe apartment building.", "Austin Energy", S.in_progress, 30.2740, -97.7415),
    ("The plaza at the farmers market gets very crowded on Saturdays, we need someone counting capacity.",
     C.crowd_monitoring, U.medium, "Farmers market plaza crowding needs monitoring.", "Parks and Recreation", S.open, 30.2640, -97.7480),
    ("Litter is piling up around the bus stop on San Jacinto, mostly cups and flyers.",
     C.waste, U.low, "Litter around San Jacinto bus stop.", "Solid Waste Services", S.open, 30.2800, -97.7400),
    ("The crosswalk paint at Trinity and 8th is faded and hard to see.",
     C.other, U.low, "Faded crosswalk paint at Trinity and 8th.", "Transportation Department", S.resolved, 30.2695, -97.7405),
    ("A park bench in Waterloo Park is missing a slat.",
     C.other, U.low, "Park bench missing a slat in Waterloo Park.", "Parks and Recreation", S.open, 30.2750, -97.7365),
    ("Noise and dust from a construction site on Colorado Street starts before 6am every day.",
     C.pollution, U.low, "Early-morning noise and dust from Colorado St site.", "Development Services", S.open, 30.2655, -97.7452),
]

NOTE_FOR = {S.in_progress: "Crew assigned; work order opened.", S.resolved: "Issue fixed and verified on-site."}


def seed(embed: bool = False) -> None:
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Complaint)):
            print("Complaints already exist; nothing to seed.")
            return
        now = datetime.now(timezone.utc)
        for i, (text, cat, urg, summary, dept, status, lat, lng) in enumerate(ROWS):
            created = now - timedelta(days=len(ROWS) - 1 - i)
            c = Complaint(
                raw_text=text, category=cat, urgency=urg, summary=summary, suggested_department=dept,
                status=status, latitude=lat, longitude=lng, prompt_version="seed", used_fallback=False,
                created_at=created, updated_at=created,
            )
            if status in NOTE_FOR:
                c.notes.append(ComplaintNote(text=NOTE_FOR[status], created_at=created + timedelta(hours=2)))
            db.add(c)
        db.commit()
        print(f"Seeded {len(ROWS)} complaints.")
    if embed:
        backfill_embeddings()


def backfill_embeddings() -> None:
    import embeddings

    print(f"Embedded {embeddings.backfill()} complaints.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed", action="store_true", help="also compute embeddings (needs LLM_API_KEY)")
    parser.add_argument("--backfill-only", action="store_true", help="only embed complaints that have no embedding")
    args = parser.parse_args()
    if args.backfill_only:
        backfill_embeddings()
    else:
        seed(embed=args.embed)
