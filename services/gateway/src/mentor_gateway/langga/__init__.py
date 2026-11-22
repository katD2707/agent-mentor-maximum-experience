"""Làng gà: the village of chickens (one chicken per subject), XP, the Arena, the study room and chicken chat.

See CONTRACTS-LANGGA.md. Importing this package registers its tables so `create_all` sees them.
"""

from mentor_gateway.langga import tables  # noqa: F401  (registers the ops.db tables)
