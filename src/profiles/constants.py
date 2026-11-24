"""Fixed choices on the profile screens, served by GET /v1/profile/options."""

from enum import StrEnum

VIBES = ["Calm chaos", "Night owl", "Overthinker", "Golden retriever", "Main character", "Old soul"]

INTEREST_SUGGESTIONS = [
    "Music", "Trekking", "Films", "Books", "Football", "Street food", "Cricket", "Gaming",
    "Coding", "Dance", "Photography", "Gym", "Art", "Anime", "Travel", "Cooking", "Poetry",
    "Stand-up",
]  # fmt: skip
MIN_INTERESTS = 3
MAX_INTERESTS = 6

PROMPT_QUESTIONS = [
    "My ideal Sunday", "Hot take", "Green flag in people", "I'll fall for you if",
    "Unpopular opinion", "The way to win me over", "A song I'd play you",
    "Most spontaneous thing I've done", "My campus comfort spot", "I'm weirdly good at",
    "Typical Friday night", "Two truths and a lie",
]  # fmt: skip
PROMPT_COUNT = 3
PROMPT_ANSWER_MAX = 120


class GuessKind(StrEnum):
    EVERYDAY = "everyday"
    HOT_TAKE = "hot_take"
    LITTLE_THING = "little_thing"


GUESS_KIND_LABELS = {
    GuessKind.EVERYDAY: "Everyday choice",
    GuessKind.HOT_TAKE: "Hot take",
    GuessKind.LITTLE_THING: "Little thing",
}
GUESS_SUGGESTIONS = {
    GuessKind.EVERYDAY: [
        "Chai or coffee?", "My go-to canteen order", "How I spend a free period",
        "Early riser or snooze-button person?",
    ],
    GuessKind.HOT_TAKE: [
        "The most overrated thing on campus", "Pineapple on pizza?", "Best season of the year",
        "Movies: theatre or laptop?",
    ],
    GuessKind.LITTLE_THING: [
        "What I always carry in my bag", "My comfort show", "The emoji I use the most",
        "What I do when I can't sleep",
    ],
}  # fmt: skip
GUESS_CARD_COUNT = 3
GUESS_OPTION_COUNT = 3
GUESS_QUESTION_MAX = 90
GUESS_OPTION_MAX = 40
# How sharp someone's blurred photo is before matching, by the viewer's right guesses on
# their cards (0-3): the photo is shrunk to this many pixels on its longer side, then
# blurred and blown up to BLUR_SIDE. Even the last step stays far too coarse to know a face.
BLUR_STEPS = (6, 8, 10, 12)
BLUR_SIDE = 600

NICKNAME_SUGGESTIONS = ["Midnight chai", "Lost playlist", "Sunset chaser", "Quiet storm"]


class Gender(StrEnum):
    WOMAN = "woman"
    MAN = "man"
    NONBINARY = "nonbinary"


class InterestedIn(StrEnum):
    WOMEN = "women"
    MEN = "men"
    EVERYONE = "everyone"


class LookingFor(StrEnum):
    SERIOUS = "serious"
    SEE_WHERE_IT_GOES = "see_where_it_goes"
    FRIENDS_FIRST = "friends_first"
    NOT_SURE = "not_sure"


LOOKING_FOR_LABELS = {
    LookingFor.SERIOUS: "Something serious",
    LookingFor.SEE_WHERE_IT_GOES: "See where it goes",
    LookingFor.FRIENDS_FIRST: "Friends first",
    LookingFor.NOT_SURE: "Not sure yet",
}


class ContactKind(StrEnum):
    """Card 7. Opens only through the last swap."""

    INSTAGRAM = "instagram"
    PHONE = "phone"


class MatchOn(StrEnum):
    SHARED_INTERESTS = "shared_interests"
    SAME_HOMETOWN = "same_hometown"
    SAME_VIBE = "same_vibe"
    NEARBY_YEARS = "nearby_years"


class Card(StrEnum):
    """The 7 cards, in order. Everyone has the same layout: see SHOWN_CARDS."""

    FIRST_NAME = "first_name"
    BRANCH = "branch"
    HOMETOWN = "hometown"
    LOOKING_FOR = "looking_for"
    VOICE = "voice"
    PHOTO = "photo"
    CONTACT = "contact"


# Shown to everyone, the same for every profile. Every other card opens only by swap.
SHOWN_CARDS = (Card.LOOKING_FOR,)
# Cards other students see on a profile, in order. Voice is optional: it's listed only for
# profiles that have one (see profiles.service._to_public).
PUBLIC_CARDS = (
    Card.FIRST_NAME, Card.BRANCH, Card.HOMETOWN, Card.LOOKING_FOR, Card.VOICE, Card.PHOTO,
    Card.CONTACT,
)  # fmt: skip
VOICE_MAX_SECONDS = 30

# Whose "Interested in" includes someone of this gender. Audience filters apply both ways.
WANTED_BY = {
    Gender.WOMAN: (InterestedIn.WOMEN, InterestedIn.EVERYONE),
    Gender.MAN: (InterestedIn.MEN, InterestedIn.EVERYONE),
    Gender.NONBINARY: (InterestedIn.EVERYONE,),
}
# The genders someone wants to see.
WANTS = {
    InterestedIn.WOMEN: (Gender.WOMAN,),
    InterestedIn.MEN: (Gender.MAN,),
    InterestedIn.EVERYONE: tuple(Gender),
}
