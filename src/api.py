from threading import Thread

from flask import Flask, render_template, request, redirect, render_template_string

import sys
import os
os.chdir(".")


import src

from src.plot import worker, get_script
from src.database import Database, ReadException
from src.outlier import OutlierDetector
from src.plot import Plot

import random, threading, webbrowser
import datetime
import logging
import json
import os

import pandas as pd
import numpy as np


TEMPLATE_PLOT = """
    <!doctype html>
    <link rel="stylesheet" type="text/css" href="/style.css">
    <html lang="en"> <!--onkeydown="keyDown()" onkeyup="keyUp()"-->

    <head>
    <meta charset="utf-8">
    <title>{{ framework }}</title>
    <style>
    html, body{ height: 100%; margin: 0;}
    body{ background-color: #e3e3e3;}

    #page_wrapper{
        display: flex;
        flex-flow: column;
        height: 100%;
    }
    #header{ 
        background-color: #CCCCCC;
        
        font-family: Helvetica, Arial, sans-serif;
        font-size: 13px;

    }
    #content{
        background-color: #DDDDDD;
        flex-grow : 1;
        height: 100%;
        border-color: #000000;
    }

    .header-elem {
        display:inline;
        margin: 5px 10px;
    }


    button,input {
        border: 1px solid transparent;
        border-radius: 4px;
        font-family: Helvetica, Arial, sans-serif;
        font-size: 12px;
        padding: 6px 12px;
        border-color: #CCCCCC;
        background-color: #FFFFFF;
        margin: 5px 0px;
    }

    .radio-button-clicked {
        background-color: #DDDDDD;
    }
    </style>
    </head>

    <body>
    <div id="page_wrapper">
        <div id="header">
            <div class="header-elem">Select variable for Outlier Correction:
            {%for var,name,clicked in variables%}
                <button class="{% if clicked %} radio-button-clicked {% else %} radio-button {% endif %}" onclick="window.location='/plot/{{var}}';">{{name}}</button><!--a class="button clicked" href="/plot/{{var}}">{{var}}</a-->
            {%endfor%}
            </div>
            <div class="header-elem">
            <label for="datetime_start">Start:</label>
            <!--input type="datetime-local" value="{{start_default}}" id="datetime_start" name="datetime_start" onchange="window.location='/plot/{{selected_variable}}?start=' + document.getElementById('datetime_start').value + '&end=' + document.getElementById('datetime_end').value"-->
            <input type="datetime-local" value="{{start_default}}" id="datetime_start" name="datetime_start">
            </div>
            <div style="display:inline">
            <label for="datetime_end">End:</label>
            <!--input type="datetime-local" value="{{end_default}}" id="datetime_end" name="datetime_end" onchange="window.location='/plot/{{selected_variable}}?start=' + document.getElementById('datetime_start').value + '&end=' + document.getElementById('datetime_end').value"-->
            <input type="datetime-local" value="{{end_default}}" id="datetime_end" name="datetime_end">
            </div>
            <button onclick="window.location='/plot/{{selected_variable}}?start=' + document.getElementById('datetime_start').value + '&end=' + document.getElementById('datetime_end').value">Update Time Period</button>
        </div>
        <div id="content">
            {{ script|safe }}
        </div>
    </div>

    <script>
        console.log("plot.html script 123");

        var shift_down = false;
        
        var el = document;
        el.onkeydown = function(evt) {
        evt = evt || window.event;
        console.log("keydown: " + evt.keyCode);
        if (evt.keyCode == 16) shift_down = true;
        };
        el.onkeyup = function(evt) {
        evt = evt || window.event;
        console.log("keyup: " + evt.keyCode);
        if (evt.keyCode == 16) shift_down = false;
        };

    </script>

    </body>
    </html>
"""

TEMPLATE_INDEX = """
    <html>
    <head>
    <style>
    html, body{ height: 100%; margin: 0;}
    body{ background-color: #e3e3e3;}

    #page_wrapper{
        display: flex;
        flex-flow: column;
        height: 100%;
    }
    #header{ 
        background-color: #CCCCCC;
        
        font-family: Helvetica, Arial, sans-serif;
        font-size: 13px;

    }
    #content{
        background-color: #DDDDDD;
        flex-grow : 1;
        height: 100%;
        border-color: #000000;
    }

    .header-elem {
        display:inline;
        margin: 5px 10px;
    }


    button,input {
        border: 1px solid transparent;
        border-radius: 4px;
        font-family: Helvetica, Arial, sans-serif;
        font-size: 12px;
        padding: 6px 12px;
        border-color: #CCCCCC;
        background-color: #FFFFFF;
        margin: 5px 0px;
    }

    .radio-button-clicked {
        background-color: #DDDDDD;
    }
    </style>
    </head>
    <!--link rel="stylesheet" type="text/css" href="/style.css"-->
    <body style="background-color: #e3e3e3">
    <form action="login" method="post" style="padding:10px; position: fixed; top: 25%; left: 50%; transform: translate(-50%, -50%); text-align: center; background-color:#f1f1f1; border-radius: 8px;">
        <div class="imgcontainer">
            <!--img src="https://iwr.tuwien.ac.at/fileadmin/_processed_/f/5/csm_bi-iwr-logo_28f68bb4f2.png" alt="Avatar" class="avatar"-->
        </div>
        <div style="font-family: Helvetica, Arial, sans-serif; font-size: 28px; color: #aaaaaa; margin-bottom: 10px;">
            Database Login
        </div>
        """
        



app = Flask(__name__, template_folder='res', static_url_path='', static_folder='../res')


@app.route('/', methods=['GET'])
def bkapp_page():
    return render_template_string(
        TEMPLATE_INDEX
        + ("""<div style="font-family: Helvetica, Arial, sans-serif; font-size: 20px; color: red; margin-bottom: 10px;">Login Failed</div>""" if "login_failed" in request.args.keys() else "") 
        + """
            <div class="container" style="color: #777777"><input type="text" placeholder="Database User" name="uname" required><input type="password" placeholder="Database Password" name="psw" required></div>
            <div class="container"background-color:#f1f1f1"><button type="submit" style="color: #777777">Login</button><!--button type="button" class="cancelbtn">Cancel</button-->
            </div>
            </form>
            {{ script|safe }}
            </body>
            </html>
        """, template="Flask")




@app.route('/login', methods=["POST"])
def login():
    """
    create database connection with credentials provided in html form
    """
    logging.info("login with user %s", request.form["uname"])
    
    try:
        Database.get_instance().connect(user=request.form["uname"], password=request.form["psw"], **config["db"])
    except Exception as e:
        return redirect("/?login_failed=1")

    
    return redirect("/plot")





@app.route('/plot', methods=["GET"])
@app.route('/plot/', methods=["GET"])
def plot():
    """
    plot using default variable
    """
    variable = list(config["related"].keys())[0] # use default variable if not specified
    return redirect("/plot/" + variable)


@app.route('/plot/<variable>', methods=["GET"])
def plot_var(variable):
    """
    plot using specified variable
    """

    # read start date form urls args if given, otherwise use default:
    start = request.args.get("start", "")
    start = datetime.datetime.now()-datetime.timedelta(days=14) if start == "" else datetime.datetime.strptime(start, "%Y-%m-%dT%H:%M") 
    
    # read end date form urls args if given, otherwise use default
    end = request.args.get("end", "")
    end = datetime.datetime.now() if end == "" else datetime.datetime.strptime(end, "%Y-%m-%dT%H:%M")

    logging.info("plot %s, %s, %s, %s", variable, start, end, config)

    try:
        Database.get_instance().read(variable, start, end, config)
    except ReadException as e:
        return """<html><body style="font-family: Helvetica, Arial, sans-serif; white-space: pre-line;">Reading from Database Failed\n\n\n\n""" + "Details:\n\n" + str(e) + "</body></html>"

    OutlierDetector(Database.get_instance().get_data(), variable, config)
    Plot(config, start, end, variable)

    script = get_script(variable, start, end, json_config)


    return render_template_string(TEMPLATE_PLOT, variables=[(k, config["names"][k], k == variable) for k in config["related"].keys()], selected_variable=variable, script=script, start_default=start.strftime("%Y-%m-%dT%H:%M"), end_default=end.strftime("%Y-%m-%dT%H:%M"), template="Flask")







if __name__ == "__main__":

    if getattr(sys, 'frozen', False):
        global application_path
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__)
    print("application_path", application_path)


    logging.basicConfig(level="INFO", format='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s')

    with open(os.path.join(application_path, "config.json")) as config:
        json_config = config.read()
        config = json.loads(json_config)
        


    os.environ["BOKEH_ALLOW_WS_ORIGIN"] = "127.0.0.1:8000"
    Thread(target=worker).start()
    
    Database()
    url = "http://127.0.0.1:8000/"

    threading.Timer(1.25, lambda: webbrowser.open(url)).start()


    

    app.run(port=8000, debug=False)


