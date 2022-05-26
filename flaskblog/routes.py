
from asyncio.windows_events import NULL
from email.mime import image
import os
from pickle import NONE
import secrets
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort
from flaskblog import app, db, bcrypt, mail
from flaskblog.forms import (RegistrationForm, LoginForm, UpdateAccountForm,
                             PostForm, RequestResetForm, ResetPasswordForm)
from flaskblog.models import Users, Post, Store
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message
import json

postName = []
trendings = ''

@app.route("/")
@app.route("/home")
def home():
    loggedin_id = -1
    page = request.args.get('page', 1, type=int)
    if current_user.is_authenticated:
        loggedin_id = current_user.id
    # posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    posts = db.engine.execute("SELECT post.*, store.liked, store.comment, store.user_id as uid \
        FROM (select users.username, users.image_file, post.* from users, post where users.id=post.user_id) as post \
        LEFT JOIN store \
        ON post.id = store.post_id \
        AND store.user_id=%s and store.liked is not %s order by post.date_posted DESC LIMIT 5;",(loggedin_id, None))
    
    posts = posts.fetchall()
    global postName
    postName.append(posts[0].title)
    postName.append(posts[0].id)
    global trendings
    trendings = db.engine.execute('select pi.id, ck.title, ck.cnt \
        from post pi, (select pt.title as title ,count(*) as cnt  \
        from store s, post pt  \
        where pt.id=s.post_id and s.liked=True \
        group by pt.title order by count(*) DESC) as ck \
        where pi.title = ck.title order by ck.cnt DESC LIMIT 3;')
    trendings = trendings.fetchall()
    print(trendings)
    return render_template('home.html', posts=posts, postName=postName, trendings=trendings)


@app.route("/about")
def about():
    return render_template('about.html', title='About', trendings=trendings, postName=postName)


@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = Users(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form, trendings=trendings, postName=postName)


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = Users.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form, trendings=trendings, postName=postName)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)

    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


@app.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account',
                           image_file=image_file, form=form, trendings=trendings, postName=postName)


def send_blogsupdate(user, post_id):
    msg = Message('New Blog Update',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    msg.body = f'''A new blog is updated by {current_user.username}, to visit link:
    {url_for('post', post_id=post_id, _external=True)}

    If you don't want anymore update click: {url_for('subscribe', _external=True)}.
    '''
    mail.send(msg)


@app.route("/post/new", methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(image_link=form.image_link.data ,title=form.title.data, content=form.content.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        user = Users.query.filter_by(subscription=True)
        for i in user:
            if i.email != current_user.email:
                send_blogsupdate(i, post.id)
        flash('Your post has been created!', 'success')
        return redirect(url_for('home'))
    return render_template('create_post.html', title='New Post',
                           form=form, legend='New Post', trendings=trendings, postName=postName)


@app.route("/post/<int:post_id>", methods=['POST', 'GET'])
def post(post_id):
    post = Post.query.get_or_404(post_id)
    comments = db.engine.execute('select u.image_file, u.username, s.comment, s.id \
        from users u, store s, post p \
        where u.id=s.user_id and p.id=s.post_id and s.comment is not %s and s.post_id=%s;',(None, post_id))
    print(comments)
    return render_template('post.html', title=post.title, post=post, comments=comments, trendings=trendings, postName=postName)


@app.route("/post/<int:post_id>/update", methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash('Your post has been updated!', 'success')
        return redirect(url_for('post', post_id=post.id))
    elif request.method == 'GET':
        form.image_link.data = post.image_link
        form.title.data = post.title
        form.content.data = post.content
    return render_template('create_post.html', title='Update Post',
                           form=form, legend='Update Post', trendings=trendings, postName=postName)


@app.route("/post/<int:post_id>/delete", methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted!', 'success')
    return redirect(url_for('home'))


@app.route("/user/<string:username>")
def user_posts(username):
    page = request.args.get('page', 1, type=int)
    user = Users.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(author=user)\
        .order_by(Post.date_posted.desc())\
        .paginate(page=page, per_page=5)
    return render_template('user_posts.html', posts=posts, user=user, trendings=trendings, postName=postName)


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)


@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = Users.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password', trendings=trendings, form=form, postName=postName)


@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = Users.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', trendings=trendings, form=form, postName=postName)

@app.route('/subscribe')
@login_required
def subscribe():
    if current_user.is_authenticated:
        s=False
        if current_user.subscription == False:
            s=True
        db.engine.execute("UPDATE Users SET subscription=%s where email=%s;",(s, current_user.email))
    return redirect(url_for('home'))

@app.route('/like_post/<int:post_id>')
@login_required
def like_post(post_id):
    # print(post_id, current_user.id)
    exist = Store.query.filter_by(post_id=post_id, user_id=current_user.id).order_by(Store.id.asc()).first()
    postStats = Post.query.get(post_id)
    if exist and exist.liked==True:
        db.engine.execute("update store set liked=%s where user_id=%s and post_id=%s;",(False, current_user.id, post_id))
        db.engine.execute("update post set likes=%s where id=%s;",(postStats.likes-1, post_id))
        return json.dumps({'likes': str(postStats.likes-1),})
    elif exist and (exist.liked==False or exist.liked is None):
        db.engine.execute("update store set liked=%s where user_id=%s and post_id=%s;",(True, current_user.id, post_id))
        db.engine.execute("update post set likes=%s where id=%s;",(postStats.likes+1, post_id))
        return json.dumps({'likes': str(postStats.likes+1),})
    else:
        db.engine.execute("INSERT INTO STORE(user_id, post_id, liked) VALUES(%s,%s,%s);",(current_user.id, post_id, True))
        db.engine.execute("update post set likes=%s where id=%s;",(postStats.likes+1, post_id))
        return json.dumps({'likes': str(postStats.likes+1),})
    return 'Success'

@app.route('/comment_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def comment_post(post_id):
    # print(post_id, current_user.id)
    k = request.get_json();
    print(k)
    exist = Store.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    postStats = Post.query.get(post_id)
    print(exist)
    if exist and exist.comment is None:
        db.engine.execute("update store set comment=%s where user_id=%s and post_id=%s;",(k, current_user.id, post_id))
        # db.engine.execute("update post set likes=%s where id=%s;",(postStats.likes+1, post_id))
        return json.dumps({'id': exist.id, 'comment': str(k), 'name': str(current_user.username), 'img_link': str(current_user.image_file),})
    else:
        db.engine.execute("INSERT INTO STORE(user_id, post_id, comment) VALUES(%s,%s,%s);",(current_user.id, post_id, k))
        # db.engine.execute("update post set likes=%s where id=%s;",(postStats.likes+1, post_id))
        exist = Store.query.filter_by(post_id=post_id, user_id=current_user.id).order_by(Store.id.desc()).first()
        return json.dumps({'id': exist.id, 'comment': str(k), 'name': str(current_user.username), 'img_link': str(current_user.image_file),})
    return json.dumps({'likes': 'If-Else none worked',})

@app.route('/del_cmmnt/<int:cmmnt_id>', methods=['GET', 'POST'])
@login_required
def del_cmmnt(cmmnt_id):
    exist = Store.query.filter_by(id=cmmnt_id).first()
    if exist.liked:
        db.engine.execute("update store set comment=%s where id=%s",(None,cmmnt_id))
        return 'Comment set to null'
    else:
        db.engine.execute("delete from store where id=%s",(cmmnt_id))
        return 'Comment record deleted'
    return 'No record updated/deleted'