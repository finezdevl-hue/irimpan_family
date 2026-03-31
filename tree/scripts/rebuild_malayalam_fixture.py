# -*- coding: utf-8 -*-
import json
from pathlib import Path


BRANCHES = [
    (
        "മാതു (വലിയവീട്)",
        [
            "ഗീവർഗീസ്", "ബ്രീജിത", "ബോബി", "സി. ഫ്രാൻസിസ്", "അപ്പു", "ചെച്ചമ്മ",
            "ഗീവർഗീസ്", "ജോസഫ്", "മാതു", "അപ്പ്", "അനു", "റെജി", "ബോബി",
            "ഗീവർഗീസ്", "സി. ജോസഫ്", "കുഞ്ഞുമോൻ", "സി. ജോസഫ്", "ബി. ജോസഫ്",
            "ഗീവർഗീസ്", "റെജി", "സി. മരിയ",
        ],
    ),
    ("ഇമ്മസ", ["[unclear]"]),
    ("ഇടപ്പ്", ["[unclear]"]),
    ("കുഞ്ഞുവൈത് (പ്രഞ്ചപ്പനം)", ["ഗീവർഗീസ്", "സ. ജോസഫ്", "കുഞ്ഞുവാരു", "സി. തോമസ്", "ബി. ജോസഫ്"]),
    ("ഒളോസേപ് (ചുണ്ടപ്പനം)", ["ഗീവർഗീസ്", "റെജി", "സി. മരിയ"]),
    ("കൊച്ചുവൈത്", ["ഒസേപ്", "അച്ചമ്മ", "തോമസ്"]),
    ("എപ്പ്", ["അനം", "മിനിക്കുട്ടി", "തോമസ്", "ഗീവർഗീസ്", "ലൂക്കോസ്", "എപ്പ്"]),
    ("ഒസേപ്", ["തോമസ്", "ലൂക്കോസ്", "ഗീവർഗീസ്", "കുഞ്ഞുമോൻ"]),
    ("[ഡ്രി. …]", ["മാതുരി", "പൗല", "[unclear]", "മറിയം", "എപ്പ്", "കൊച്ചുവൈത്"]),
]


def main():
    fixture = []
    pk = 1
    created_at = "2024-01-01T00:00:00Z"
    head_pks = []

    for name, _children in BRANCHES:
        fixture.append(
            {
                "model": "tree.person",
                "pk": pk,
                "fields": {
                    "first_name": name,
                    "last_name": "",
                    "gender": "O",
                    "birth_place": "",
                    "bio": "Malayalam family branch imported from the provided family chart.",
                    "photo": "photos/download.jpg",
                    "father": None,
                    "mother": None,
                    "spouse": None,
                    "created_at": created_at,
                },
            }
        )
        head_pks.append(pk)
        pk += 1

    for head_pk, (name, children) in zip(head_pks, BRANCHES):
        for child in children:
            fixture.append(
                {
                    "model": "tree.person",
                    "pk": pk,
                    "fields": {
                        "first_name": child,
                        "last_name": "",
                        "gender": "O",
                        "birth_place": "",
                        "bio": f"Child listed under {name} in the provided Malayalam family chart.",
                        "photo": "photos/download.jpg",
                        "father": head_pk,
                        "mother": None,
                        "spouse": None,
                        "created_at": created_at,
                    },
                }
            )
            pk += 1

    output_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_data.json"
    output_path.write_text(
        json.dumps(fixture, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(fixture)} people to {output_path}")


if __name__ == "__main__":
    main()
