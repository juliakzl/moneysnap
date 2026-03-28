"""
Rule-based transaction categorization.
Rules are matched case-insensitively against the merchant name.
Add new rules here — they run before AI categorization, which handles everything else.
"""

# (substring_to_match, category)
RULES = [
    # Housing
    ("westermann", "Rent"),

    # Internal transfers between own accounts — excluded from income/expense/growth stats
    ("flexible cash", "Internal Transfer"),
    ("from flexible cash", "Internal Transfer"),

    # Investments / transfers — add rules here to match your own name as it appears in bank transfers
    # ("your full name & partner name", "Joint Account"),
    # ("your full name", "Investments"),
    ("Advents", "Investments"),

    # Entertainment
    ("kino", "Entertainment"),
    ("cinema", "Entertainment"),

    # Groceries
    ("edeka", "Groceries"),
    ("rewe", "Groceries"),

    # Shopping
    ("vinted", "Vinted"),

    # Add custom rules here for merchants you want to tag with a person's name or custom category
    # ("some merchant", "Friend Name"),

    # Subscriptions
    ("spotify", "Subscriptions"),
    ("vodafone", "Subscriptions"),
    ("fraenk", "Subscriptions"),
    ("anthropic", "Subscriptions"),

    # Transport
    ("db vertrieb", "Transport"),
    ("uber", "Transport"),
    ("bolt", "Transport"),
    ("ryinair", "Transport"),
    ("flight", "Transport"),
    ("fly", "Transport"),

    # Dining — keyword matches
    ("coffee", "Dining"),
    ("cafe", "Dining"),
    ("café", "Dining"),
    ("restaurant", "Dining"),
    ("bistro", "Dining"),
    ("bakery", "Dining"),
    ("bäckerei", "Dining"),
]
