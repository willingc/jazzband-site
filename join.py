from decouple import config
from flask import (Flask, request, g, session, redirect, url_for, abort,
                   render_template)
from flask.ext.github import GitHub, GitHubError
from flask.ext.session import Session
import redis

# Set these values in the .env file or env vars
GITHUB_CLIENT_ID = config('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = config('GITHUB_CLIENT_SECRET', '')
GITHUB_ORG_ID = config('GITHUB_ORG_ID', 'jazzband')
GITHUB_SCOPE = config('GITHUB_SCOPE', 'read:org,user:email')
GITHUB_TEAM_ID = config('GITHUB_TEAM_ID', 0, cast=int)
GITHUB_ADMIN_TOKEN = config('GITHUB_ADMIN_TOKEN', '')

SECRET_KEY = config('SECRET_KEY', 'dev key')
DEBUG = config('DEBUG', False, cast=bool)

SESSION_TYPE = 'redis'
SESSION_COOKIE_NAME = 'jazzhands'
SESSION_COOKIE_SECURE = not DEBUG
SESSION_USE_SIGNER = config('SESSION_USE_SIGNER', True, cast=bool)
SESSION_REDIS = redis.from_url(config('REDIS_URL', 'redis://127.0.0.1:6379/0'))
PERMANENT_SESSION_LIFETIME = 60 * 60

# setup flask
app = Flask(__name__)

# load decoupled config variables
app.config.from_object(__name__)

# setup github-flask
github = GitHub(app)

# setup session store
Session(app)


@app.before_request
def before_request():
    g.user_access_token = session.get('user_access_token', None)


@github.access_token_getter
def token_getter():
    return g.user_access_token


@app.route('/callback')
@github.authorized_handler
def authorized(access_token):
    next_url = request.args.get('next') or url_for('index')
    if access_token is None:
        return redirect(next_url)
    session['user_access_token'] = access_token
    return redirect(next_url)


def add_to_org(user_login):
    resource = 'teams/{}/memberships/{}'.format(GITHUB_TEAM_ID, user_login)
    return github.put(resource, access_token=GITHUB_ADMIN_TOKEN)


def is_member(user_login):
    resource = 'orgs/{}/members/{}'.format(GITHUB_ORG_ID, user_login)
    try:
        github.get(resource, access_token=GITHUB_ADMIN_TOKEN)
        return True
    except GitHubError:
        return False


def verified_emails():
    return any([email for email in github.get('user/emails')
                if email.get('verified', False)])


@app.errorhandler(403)
def forbidden():
    return render_template('forbidden.html')


@app.errorhandler(500)
def error():
    return render_template('error.html')


@app.route('/')
def index():
    if g.user_access_token:
        user_login = github.get('user').get('login', None)

        # fail if something went wrong
        if user_login is None:
            abort(500)

        # deny permission if there are no verified emails
        if not verified_emails():
            abort(403)

        membership = None
        user_is_member = is_member(user_login)

        if not user_is_member:
            try:
                membership = add_to_org(user_login)
            except GitHubError:
                pass

        return render_template('index.html',
                               next_url='https://github.com/jazzband',
                               membership=membership,
                               org_id=GITHUB_ORG_ID,
                               is_member=user_is_member)
    else:
        return github.authorize(scope=app.config['GITHUB_SCOPE'])


if __name__ == '__main__':
    app.run(debug=True)