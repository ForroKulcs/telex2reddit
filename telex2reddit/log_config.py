import json
import logging.config
from pathlib import Path


def create_handler_bugsnag(config: dict):
    import bugsnag.handlers  # pip install bugsnag

    bugsnag.configure(**config['configure'])
    handler_config = config['handler']
    handler = bugsnag.handlers.BugsnagHandler(**handler_config)
    if ('level' not in handler_config) and ('level' in config):
        handler.setLevel(config.get('level', logging.INFO))
    return handler


def create_handler_rollbar(config: dict):
    import rollbar.logger  # pip install rollbar

    rollbar.SETTINGS['allow_logging_basic_config'] = config.get('allow_logging_basic_config', False)
    return rollbar.logger.RollbarHandler(**config['handler'])


def create_handler_sentry(config: dict):
    import raven.handlers.logging  # pip install raven

    return raven.handlers.logging.SentryHandler(**config['handler'])


def create_handler_glitchtip(config: dict):
    return create_handler_sentry(config)


def load_handlers(handler_path: Path, logger_name: str = ''):
    for path in handler_path.glob('*'):
        if path.is_dir():
            load_handlers(path, path.name if logger_name == '' else logger_name + '.' + path.name)
        else:
            if path.suffix.lower() == '.json':
                config = json.loads(path.read_text())
                if config.get('enabled', True):
                    lower_filename = path.stem.lower()
                    loader_function_name = 'create_handler_' + lower_filename
                    handler_creator = globals().get(loader_function_name, None)
                    if callable(handler_creator):
                        handler = handler_creator(config)
                        logging.getLogger(logger_name).addHandler(handler)


def load_log_config(config_root_path: Path, handler_root_path: Path = None):
    if config_root_path:
        for path in config_root_path.glob('*'):
            if path.is_file():
                if path.suffix.lower() == '.json':
                    config = json.loads(path.read_text())
                    for handler in config.get('handlers', {}).values():
                        if 'filename' in handler:
                            Path(handler['filename']).parent.mkdir(exist_ok=True, parents=True)
                    logging.config.dictConfig(config)
                elif path.suffix.lower() == '.ini':
                    logging.config.fileConfig(path, disable_existing_loggers=False)

    if handler_root_path:
        load_handlers(handler_root_path, '')
