"""Study domain errors shared by the API, transports, and storage."""


class StudyError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)
