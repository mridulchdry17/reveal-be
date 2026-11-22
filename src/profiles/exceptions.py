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
