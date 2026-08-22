"""The blind-spot detector: repeated demand nobody serves yet."""

import time

from hunter.intent import qualify
from hunter.lead import Lead
from hunter.niche import MIN_SAMPLE, clusters, render


def post(title, body="", hours_old=2.0, comments=1, ident=None):
    return qualify(Lead("test", ident or title[:20], title, body,
                        created_utc=time.time() - hours_old * 3600,
                        extra={"num_comments": comments}))


# Filler exists only to get past the MIN_SAMPLE guard, so its words are unique
# per post: any shared phrasing would form a cluster of its own - correctly, the
# detector counts repetition - and drown the behaviour under test. Real corpora
# are messier; the demo-corpus test below covers that case.
def filler(count, start=0):
    """Qualified posts with no vocabulary in common."""
    rows = []
    for index in range(start, start + count):
        tokens = " ".join(f"{stem}{index:03d}" for stem in
                          ("zeta", "kappa", "omega", "sigma", "delta", "theta", "lambda"))
        rows.append(post(
            f"[HIRING] zeta{index:03d} kappa{index:03d}, budget ${200 + 17 * index}",
            tokens, ident=f"filler-{index}"))
    return rows


# Five different people asking for the same thing in their own words. The only
# phrase they share is the one that names the niche.
_DM_POSTS = [
    ("[HIRING] auto-answer our instagram dms about prices, $180",
     "boutique in Lisbon, five identical questions arrive every morning"),
    ("Need help with repetitive instagram dms for my bakery, paying $150",
     "cake prices and opening hours, over and over, I cannot keep up"),
    ("[HIRING] someone to handle instagram dms automatically - budget $220",
     "skincare shop, sizes and shipping times asked all day long"),
    ("Looking for a way to answer instagram dms without hiring a person, $200",
     "gym memberships, same three requests morning and evening"),
    ("[TASK] instagram dms triage for a small studio - $120",
     "forward the real leads to me, answer the rest from a script"),
]


def niche_posts(count, comments=1):
    return [post(title, body, comments=comments, ident=f"dm-{index}")
            for index, (title, body) in enumerate(_DM_POSTS[:count])]


def test_it_refuses_to_name_a_niche_from_a_tiny_sample():
    leads = [post("[HIRING] auto-answer instagram dms, $200", "same questions all day",
                  ident=str(index)) for index in range(4)]
    ranked, analysed = clusters(leads)
    assert analysed < MIN_SAMPLE
    rendered = render(ranked, analysed, 14)
    assert "Pas encore de quoi conclure" in rendered
    assert str(MIN_SAMPLE - analysed) in rendered


def test_a_request_outside_the_catalogue_still_counts_as_demand():
    # The catalogue penalty pushes this below the answering threshold - which is
    # exactly how an unserved niche stays invisible. demand_score keeps it.
    lead = post("[HIRING] Auto reply to whatsapp messages with our price list - $120",
                "customers ask for prices all day, then notify us")
    assert lead.tier == "IGNORE"
    assert lead.demand_score >= 45


def test_a_repeated_uncovered_ask_outranks_generic_single_words():
    leads = filler(26) + niche_posts(3)
    ranked, analysed = clusters(leads, days=14)
    assert analysed >= MIN_SAMPLE

    found = next(cluster for cluster in ranked if cluster.term == "instagram dms")
    assert found.count == 3
    assert found.blind_spot == 1.0      # nothing in the catalogue covers it
    words = [cluster for cluster in ranked if " " not in cluster.term]
    assert all(found.score > cluster.score for cluster in words if cluster.count <= found.count)


def test_the_verdict_names_the_blind_spot_when_the_top_cluster_is_uncovered():
    leads = filler(26) + niche_posts(5)
    ranked, analysed = clusters(leads, days=14)
    rendered = render(ranked, analysed, 14)
    assert ranked[0].term == "instagram dms"
    assert "angle mort" in rendered


def test_a_term_nobody_repeats_is_not_a_cluster():
    leads = filler(26) + [post("[HIRING] need a didgeridoo tuned, $90", "urgent", ident="one-off")]
    ranked, _ = clusters(leads, days=14)
    assert all("didgeridoo" not in cluster.term for cluster in ranked)


def test_pairs_win_over_the_words_inside_them():
    leads = filler(26)
    for index, context in enumerate(("restaurant", "pizzeria", "florist", "pharmacy")):
        leads.append(post(f"[HIRING] whatsapp orders into a spreadsheet for my {context}, $250",
                          f"forty {context} orders a day typed by hand, one row each",
                          ident=f"wa-{index}"))
    ranked, _ = clusters(leads, days=14)
    terms = [cluster.term for cluster in ranked]
    assert "whatsapp orders" in terms
    assert "whatsapp" not in terms and "orders" not in terms


def test_competition_lowers_the_score():
    from hunter.niche import Cluster

    quiet = Cluster("instagram dms", niche_posts(3, comments=0))
    crowded = Cluster("instagram dms", niche_posts(3, comments=25))
    assert quiet.score > crowded.score
    # and a post nobody answered is worth answering: the pipeline agrees
    assert all(lead.demand_score > 0 for lead in quiet.leads)


def test_the_demo_corpus_surfaces_its_planted_niche():
    from hunter.offer import prepare
    from hunter.sources import fetch_demo

    leads = [prepare(qualify(row)) for row in fetch_demo().leads]
    ranked, analysed = clusters(leads, days=14)
    assert analysed >= MIN_SAMPLE
    assert "instagram dms" == ranked[0].term
    assert ranked[0].to_dict()["ids"]
