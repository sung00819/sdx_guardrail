import json, csv, sys
R = "/Users/seong-yumin/SDX/sdx_rlver_wt/out/rlver/"
SETS = {"plain": "1031)plain_len_test_30b", "bank": "1025)bank_jev_test_30b", "riskplan": "1025)bank_jev_plan_test_30b_riskplan"}
grp = {r["id"]: r["group"] for r in csv.DictReader(open("/Users/seong-yumin/SDX/sdx_rlver_wt/data/rlver/backgrounds_v2.csv"))}
out = open(sys.argv[1], "w")
for name, d in SETS.items():
    gold = {}
    try:
        for l in open(R + d + "/turn_gold.jsonl"):
            g = json.loads(l); gold[(g["id"], g["setting"])] = g["labels"]
    except FileNotFoundError:
        pass
    for l in open(R + d + "/episodes.jsonl"):
        e = json.loads(l)
        users = []
        gl = gold.get((e["id"], e["setting"]))
        for i, t in enumerate(e["turns"]):
            users.append(t["user"])
            out.write(json.dumps({"set": name, "id": e["id"], "setting": e["setting"], "group": grp.get(e["id"]), "i": i,
                "user": t["user"], "window": users[-3:], "bot": t.get("bot"), "jev": t.get("jev"),
                "risk": (t.get("route") or {}).get("risk"), "sticky": (t.get("route") or {}).get("sticky"),
                "gold": list(gl[i].keys()) if gl and i < len(gl) else None}, ensure_ascii=False) + "\n")
