"""Ошибки прикладных сервисов, пригодные для ответа пользователю."""


class BotError(Exception):
    code = "operation_failed"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.details = details


class CommandError(BotError):
    code = "invalid_command"


class DocumentNotFoundError(BotError):
    code = "document_not_found"


class AmbiguousDocumentError(BotError):
    code = "ambiguous_document"


class DocumentTextError(BotError):
    code = "document_text_unavailable"


class DocumentNotReadyError(BotError):
    code = "document_not_ready"


class LanguageDetectionError(BotError):
    code = "language_unknown"


class StorageUnavailableError(BotError):
    code = "storage_unavailable"


class DatabaseUnavailableError(BotError):
    code = "database_unavailable"


class TranslationModelError(BotError):
    code = "translation_model_unavailable"


class TranslationError(BotError):
    code = "translation_failed"


class VoiceUnavailableError(BotError):
    code = "voice_unavailable"


class SynthesisError(BotError):
    code = "synthesis_failed"


class RecognitionError(BotError):
    code = "recognition_failed"


class ResourceUnavailableError(BotError):
    code = "nlp_resource_unavailable"
