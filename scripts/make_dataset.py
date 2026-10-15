"""Generate the labelled synthetic ticket set: data/tickets_labelled.jsonl (96 tickets).

    python scripts/make_dataset.py

Synthetic on purpose (no customer data): 8 categories x 12 tickets, half Polish, half English,
written from several templates per category with random products, order numbers, delays and
personal data (fake e-mails, phones, IBANs) so the masking is exercised too. Labels come from
the template, not from a model.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261015

PRODUCTS_EN = ["Original shelf", "wardrobe", "sideboard", "TV stand", "bookcase", "shoe rack",
               "chest of drawers", "desk"]
PRODUCTS_PL = ["regał Original", "szafa", "komoda", "szafka RTV", "regał na książki",
               "szafka na buty", "biurko", "kredens"]
NAMES = ["anna.kowalska", "piotr.nowak", "m.wisniewska", "tomasz.zielinski", "kasia.lewandowska",
         "j.kaminski", "ola.wojcik", "marek.dabrowski"]

# (category, language, urgency, template)
TEMPLATES = [
    ("delivery_delay", "en", "normal",
     "Hi, my {p} (order {o}) was supposed to arrive {d} days ago and the tracking hasn't "
     "moved. When will it be delivered?"),
    ("delivery_delay", "en", "high",
     "This is the third time I'm writing! Order {o} is now {dd} days late and nobody answers. "
     "I took a day off for a delivery that never came. Call me: {ph}."),
    ("delivery_delay", "pl", "normal",
     "Dzień dobry, zamówienie {o} ({p}) miało być {d} dni temu, a status się nie zmienia. "
     "Kiedy mogę się spodziewać dostawy?"),
    ("delivery_delay", "pl", "high",
     "Piszę już kolejny raz. Zamówienie {o} spóźnia się {dd} dni, nikt nie odbiera telefonu. "
     "Proszę o pilny kontakt: {ph}."),
    ("damaged_item", "en", "high",
     "The {p} from order {o} arrived with a cracked panel and a broken hinge. Photos attached. "
     "Please advise. {em}"),
    ("damaged_item", "en", "high",
     "Two boxes of my {p} were crushed and one shelf is missing entirely. Order {o}."),
    ("damaged_item", "pl", "high",
     "Przyszła {p} z zamówienia {o}, ale front jest pęknięty, a jednej półki brakuje. "
     "Zdjęcia w załączniku. {em}"),
    ("damaged_item", "pl", "high",
     "Paczka z zamówienia {o} była zgnieciona, {p} ma porysowany blat. Co dalej?"),
    ("assembly_help", "en", "low",
     "I'm assembling my {p} and can't find which screws go into the back panel. Is there a "
     "video guide?"),
    ("assembly_help", "en", "normal",
     "Step 7 of the {p} manual doesn't match the parts I have. Order {o}. Could you help?"),
    ("assembly_help", "pl", "low",
     "Składam {p} i nie wiem, które kołki są do drzwiczek. Czy jest instrukcja wideo?"),
    ("assembly_help", "pl", "normal",
     "Krok 5 instrukcji do produktu {p} nie zgadza się z elementami w paczce. Zamówienie {o}."),
    ("return_refund", "en", "normal",
     "I'd like to return the {p} from order {o} within the 100-day trial. Refund to {ib}, "
     "please."),
    ("return_refund", "en", "normal",
     "The {p} doesn't fit our room after all. How do I send it back and get my money back? "
     "Order {o}."),
    ("return_refund", "pl", "normal",
     "Chcę odstąpić od umowy i zwrócić {p} (zamówienie {o}). Zwrot proszę na konto {ib}."),
    ("return_refund", "pl", "normal",
     "{p} jednak nie pasuje do wnętrza. Jak mogę ją odesłać i odzyskać pieniądze? "
     "Zamówienie {o}."),
    ("order_change", "en", "normal",
     "Can I change the delivery address for order {o}? It hasn't shipped yet. {em}"),
    ("order_change", "en", "high",
     "Please cancel order {o} before it ships - the delivery is booked for tomorrow and I "
     "ordered the wrong colour."),
    ("order_change", "pl", "normal",
     "Czy mogę zmienić kolor produktu {p} w zamówieniu {o}? Jeszcze nie zostało wysłane."),
    ("order_change", "pl", "high",
     "Proszę pilnie anulować zamówienie {o}, dostawa jest jutro, a pomyliłem wymiary."),
    ("payment_invoice", "en", "normal",
     "I need a VAT invoice for order {o} issued to my company. Please send it to {em}."),
    ("payment_invoice", "en", "normal",
     "My card was charged twice for order {o}. Can you check and refund the duplicate?"),
    ("payment_invoice", "pl", "normal",
     "Proszę o fakturę VAT na firmę do zamówienia {o}. Dane prześlę mailem: {em}."),
    ("payment_invoice", "pl", "normal",
     "Płatność za zamówienie {o} została pobrana dwa razy. Proszę o sprawdzenie."),
    ("product_question", "en", "low",
     "Is the {p} available in 240 cm width and in walnut? What's the current lead time?"),
    ("product_question", "en", "low",
     "What material is the {p} made of, and can it hold a 50 kg TV?"),
    ("product_question", "pl", "low",
     "Czy {p} jest dostępna w szerokości 180 cm i w kolorze dąb? Jaki jest czas realizacji?"),
    ("product_question", "pl", "low",
     "Z jakiego materiału jest {p} i ile kilogramów uniesie jedna półka?"),
    ("other", "en", "low",
     "Hi, do you have a showroom in Warsaw where I could see the materials?"),
    ("other", "en", "low",
     "I'd like to unsubscribe from your newsletter. {em}"),
    ("other", "pl", "low",
     "Czy macie showroom w Krakowie, gdzie można zobaczyć próbki kolorów?"),
    ("other", "pl", "low",
     "Proszę o wypisanie mnie z newslettera. {em}"),
]


def fill(template: str, lang: str, rng: random.Random) -> str:
    products = PRODUCTS_PL if lang == "pl" else PRODUCTS_EN
    return template.format(
        p=rng.choice(products),
        o=f"TY-{rng.randint(1_000_000, 9_999_999)}",
        d=rng.randint(2, 5),
        dd=rng.randint(9, 20),
        ph=f"+48 {rng.randint(500, 899)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
        em=f"{rng.choice(NAMES)}@example.com",
        ib="PL" + "".join(str(rng.randint(0, 9)) for _ in range(2)) + " "
           + " ".join(f"{rng.randint(0, 9999):04d}" for _ in range(6)),
    )


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    for cat in dict.fromkeys(t[0] for t in TEMPLATES):
        for lang in ("en", "pl"):
            options = [t for t in TEMPLATES if t[0] == cat and t[1] == lang]
            for i in range(6):
                _, _, urgency, tpl = options[i % len(options)]
                rows.append({"ticket_id": f"S-{len(rows) + 1:03d}", "channel": "email",
                             "text": fill(tpl, lang, rng), "category": cat,
                             "urgency": urgency, "language": lang})
    out = ROOT / "data" / "tickets_labelled.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")
    print(f"{len(rows)} tickets -> {out}")


if __name__ == "__main__":
    main()
