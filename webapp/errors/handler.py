"""
Handlers for the various errors that can occur in the webapp. Logs the error and returns a template.
"""

from datetime import datetime
from pathlib import Path
import shutil

import daiquiri
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from webapp import app
from webapp.home.exceptions import EMLFileNotFound, LockOwnedByAGroup, LockOwnedByAnotherUser, DeprecatedCodeError, \
    NodeWithGivenIdNotFound, InvalidFilename, MissingDataFiles
from webapp.config import Config
import webapp.auth.user_data as user_data
from webapp.pages import *


logger = daiquiri.getLogger('handler: ' + __name__)
errors = Blueprint('errors', __name__, template_folder='templates')


def log_error(error):
    if current_user and hasattr(current_user, 'get_username'):
        logger.error(error, USER=current_user.get_username())
        if hasattr(error, 'original_exception'):
            logger.error(error.original_exception, USER=current_user.get_username())
    else:
        logger.error(error)
        if hasattr(error, 'original_exception'):
            logger.error(error.original_exception)


@app.errorhandler(400)
def bad_request(error):
    log_error(error)
    return render_template('400.html'), 400


@app.errorhandler(401)
def bad_request(error):
    log_error(error)
    return render_template('401.html'), 401


@app.errorhandler(404)
def bad_request(error):
    log_error(error)
    if request and request.url:
        logger.error(f'404 request.url: {request.url}')
    return render_template('404.html'), 404


def backup_model_file():
    try:
        user_path = Path(user_data.get_user_folder_name())

        backup_path = Path(user_data.get_user_error_backups_folder_name())
        backup_path.mkdir(parents=True, exist_ok=True)

        active_document = user_data.get_active_document()
        if not active_document:
            return

        active_document = f'{active_document}.json'
        src = user_path / active_document

        if not src.exists():
            log_error(f'backup_model_file: Source file does not exist: {src}')
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
        backup_filename = f'{timestamp} {active_document}'
        dst = backup_path / backup_filename

        shutil.copy2(src, dst)
        log_error(f'Model file backed up as error_backups/{backup_filename}')
    except Exception as e:
        log_error(f'Unable to backup json file {active_document if "active_document" in locals() else "unknown"}: {e}')


@app.errorhandler(500)
def bad_request(error):
    backup_model_file()
    log_error(error)
    return render_template('500.html'), 500


@app.errorhandler(EMLFileNotFound)
def handle_eml_file_not_found(error):
    log_error('EML file not found: {0}'.format(error.message))
    user_data.set_active_document(None)
    return redirect(url_for(PAGE_INDEX))


@app.errorhandler(InvalidFilename)
def handle_invalid_filename(error):
    log_error('Invalid filename: {0}'.format(error.message))
    user_data.set_active_document(None)
    return render_template('invalid_filename_error.html',
                           message=error.message)


@app.errorhandler(NodeWithGivenIdNotFound)
def handle_node_with_given_id_not_found(error):
    backup_model_file()
    log_error('Node with given ID not found: {0}'.format(error.message))
    return render_template('node_with_given_id_not_found.html'), 404


@app.errorhandler(LockOwnedByAGroup)
def handle_locked_by_a_group(error):
    log_error('Attempt to access a locked document: {0}'.format(error.message))
    return render_template('locked_by_group.html',
                           package_name=error.package_name,
                           locked_by=error.user_name), 403


@app.errorhandler(LockOwnedByAnotherUser)
def handle_lock_is_not_owned_by_user(error):
    log_error('Attempt to access a locked document: {0}'.format(error.message))
    return render_template('locked_by_another.html',
                           package_name=error.package_name,
                           locked_by=error.user_name,
                           lock_timeout=Config.COLLABORATION_LOCK_INACTIVITY_TIMEOUT_MINUTES), 403


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    log_error('**** A CSRF error occurred: {0}'.format(error.description))
    return render_template('401.html'), 403


@app.errorhandler(DeprecatedCodeError)
def handle_deprecated_code_error(error):
    log_error('**** A deprecated code error occurred: {0}'.format(error.message))
    return render_template('deprecated_code_error.html', message=error.message), 403


@app.errorhandler(MissingDataFiles)
def handle_missing_data_files(error):
    log_error(
        'Missing data files for document "{0}": data tables={1}'.format(
            error.document_name,
            error.missing_data_tables,
        )
    )
    return render_template(
        'missing_data_files_error.html',
        document_name=error.document_name,
        missing_data_tables=error.missing_data_tables,
    ), 422
