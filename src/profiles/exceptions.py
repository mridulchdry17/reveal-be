from src.exceptions import Conflict, DomainError, NotFound


class ProfileIncomplete(Conflict):
    code = "profile_incomplete"


class PromptNotFound(NotFound):
    code = "prompt_not_found"


class PhotoNotFound(NotFound):
    code = "photo_not_found"


class PhotoTooLarge(DomainError):
    status_code = 413
    code = "photo_too_large"


class NotAPhoto(DomainError):
    status_code = 422
    code = "not_a_photo"


class VoiceNoteNotFound(NotFound):
    code = "voice_note_not_found"


class VoiceNoteTooLarge(DomainError):
    status_code = 413
    code = "voice_note_too_large"


class NotAVoiceNote(DomainError):
    status_code = 422
    code = "not_a_voice_note"


class GuessCardNotFound(NotFound):
    """Missing, yours, or someone you can't see right now: all look the same."""

    code = "guess_card_not_found"


class GuessCardNotGuessed(Conflict):
    """Liking a guess card needs a guess on it first."""

    code = "guess_card_not_guessed"


class HintAlreadyUsed(Conflict):
    """One hint a night, on one card."""

    code = "hint_already_used"


class AlreadyGuessed(Conflict):
    """One try per card."""

    code = "already_guessed"
