import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("SELECT symbol, SUM(shares), price FROM buy WHERE user_id = ? GROUP BY symbol", session["user_id"])
    cash = float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"])

    for i in range(len(rows)):
        rows[i]["shares"] = rows[i].pop("SUM(shares)")

        rows[i]["shares"] = int(rows[i]["shares"])
        rows[i]["price"] = float(rows[i]["price"])
        rows[i]["name"] = lookup(rows[i]["symbol"])["name"]

    shares = list()

    for i in range(len(rows)):
        if rows[i]["shares"] != 0:
            shares.append(rows[i])

    return render_template("index.html", shares = shares, cash = cash,
                            total = (cash + sum([shares[i]["price"]*shares[i]["shares"] for i in range(len(shares))])) )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        if not lookup(request.form.get("symbol")):
            return apology("symbol does not exist")

        try:
            if int(request.form.get("shares")) <= 0:
                return apology("invalid value of shares")

        except ValueError:
            return apology("invalid value of shares")

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        price = lookup(symbol)["price"]
        date = datetime.date.today()
        time = datetime.datetime.now().strftime("%H:%M:%S")

        cash_start = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        if cash_start - float(price)*int(shares) < 0:
            return apology("insufficient funds")

        else:
            cash_end = cash_start - float(price)*int(shares)
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_end, session["user_id"])

        db.execute("""INSERT INTO buy
                        (user_id, symbol, shares, price, date, time)
                      VALUES
                        (?, ?, ?, ?, ?, ?)""",
                        session["user_id"], symbol, shares, price, date, time)

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute("SELECT symbol, shares, price, date, time FROM buy WHERE user_id = ?", session["user_id"])

    return render_template("history.html", rows = rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":

        result_of_searching = lookup(request.form.get("symbol"))

        if result_of_searching:
            return render_template("quoted.html", name = result_of_searching["name"],
                                                  price = usd(result_of_searching["price"]),
                                                  symbol = result_of_searching["symbol"])

        else:
            return apology("symbol does not exist")

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 403)

        elif not request.form.get("password"):
            return apology("must provide password", 403)

        elif not request.form.get("confirm_password"):
            return apology("must confirm password", 403)

        rows = db.execute("SELECT username FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) != 0:
            return apology("exist username", 403)

        elif not (request.form.get("password") == request.form.get("confirm_password")):
            return apology("passwords not mach", 403)

        else:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"),
                        generate_password_hash(request.form.get("password")))

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        try:
            if int(request.form.get("shares")) <= 0:
                return apology("invalid value of shares")

        except ValueError:
            return apology("invalid value of shares")

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        price = lookup(symbol)["price"]
        date = datetime.date.today()
        time = datetime.datetime.now().strftime("%H:%M:%S")

        real_shares = db.execute("SELECT SUM(shares) FROM buy WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]["SUM(shares)"]

        if int(shares) > int(real_shares):
            return apology("shares more than real shares")

        cash_start = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]


        cash_end = cash_start + float(price)*int(shares)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_end, session["user_id"])

        if int(real_shares) > 0:
            db.execute("""INSERT INTO buy
                            (user_id, symbol, shares, price, date, time)
                        VALUES
                            (?, ?, ?, ?, ?, ?)""",
                            session["user_id"], symbol, -int(shares), price, date, time)

        return redirect("/")

    else:
        rows = db.execute("SELECT symbol, SUM(shares) FROM buy WHERE user_id = ? GROUP BY symbol", session["user_id"])
        symbols = list()

        for row in rows:
            if row["SUM(shares)"] != 0:
                symbols.append(row)

        return render_template("sell.html", symbols = symbols)
