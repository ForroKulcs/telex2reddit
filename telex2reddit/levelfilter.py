import logging.config


class LevelFilter(logging.Filter):
    def filter(self, record):
        return record.levelno == self.get_filter_level()

    def get_filter_level(self):
        raise NotImplementedError()


class NotsetLevelFilter(LevelFilter):
    def get_filter_level(self):
        return logging.NOTSET


class DebugLevelFilter(LevelFilter):
    def get_filter_level(self):
        return logging.DEBUG


class InfoLevelFilter(LevelFilter):
    def get_filter_level(self):
        return logging.INFO


class WarningLevelFilter(LevelFilter):
    def get_filter_level(self):
        return logging.WARNING


class ErrorLevelFilter(LevelFilter):
    def get_filter_level(self):
        return logging.ERROR


class CriticalLevelFilter(LevelFilter):
    def get_filter_level(self):
        return logging.CRITICAL
