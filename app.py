# -*- coding: utf-8 -*-
"""view module prilog application

     * view function, and run Flask




"""
from flask import Flask, request, jsonify
import os
import re
import subprocess
import time as tm
import analyze as al
import common as cm
import state_list as state

SERVER_ERROR_STATE = False

# movie download directory
stream_dir = "tmp/"
if not os.path.exists(stream_dir):
    os.mkdir(stream_dir)

# analyze result save as cache directory
cache_dir = "cache/"
if not os.path.exists(cache_dir):
    os.mkdir(cache_dir)

# save analyzing id as file directory
download_dir = "download/"
if not os.path.exists(download_dir):
    os.mkdir(download_dir)

# waiting analyze id as file directory
dl_queue_dir = "download/queue/"
if not os.path.exists(dl_queue_dir):
    os.mkdir(dl_queue_dir)

# save analyzing id as file directory
dl_ongoing_dir = "download/ongoing/"
if not os.path.exists(dl_ongoing_dir):
    os.mkdir(dl_ongoing_dir)

# save analyzing id as file directory
dl_pending_dir = "download/pending/"
if not os.path.exists(dl_pending_dir):
    os.mkdir(dl_pending_dir)

# waiting analyze id as file directory
queue_dir = "queue/"
if not os.path.exists(queue_dir):
    os.mkdir(queue_dir)

# save analyzing id as file directory
pending_dir = "pending/"
if not os.path.exists(pending_dir):
    os.mkdir(pending_dir)


def get_rest_result(title, time_line, time_line_enemy, time_data, total_damage, debuff_value):
    rest_result = {"title": title, "timeline": time_line, "timeline_enemy": time_line_enemy, "process_time": time_data,
                   "total_damage": total_damage, "debuff_value": debuff_value}

    if time_line:
        rest_result["timeline_txt"] = "\r\n".join(time_line)
        if time_line_enemy:
            rest_result["timeline_txt_enemy"] = "\r\n".join(time_line_enemy)
        else:
            rest_result["timeline_txt_enemy"] = False

        if debuff_value:
            rest_result["timeline_txt_debuff"] = "\r\n".join(list(
                map(lambda x: "↓{} {}".format(str(debuff_value[x[0]][0:]).rjust(3, " "), x[1]),
                    enumerate(time_line))))
        else:
            rest_result["timeline_txt_debuff"] = False
    else:
        rest_result["timeline_txt"] = False
        rest_result["timeline_txt_enemy"] = False
        rest_result["timeline_txt_debuff"] = False

    return rest_result


app = Flask(__name__)
app.config.from_object(__name__)
app.config["SECRET_KEY"] = "zJe09C5c3tMf5FnNL09C5e6SAzZuY"
app.config["JSON_AS_ASCII"] = False


@app.route("/rest/analyze", methods=["POST", "GET"])
def rest_analyze():
    status = state.ERR_REQ_UNEXPECTED
    is_parent = False
    rest_result = {}
    ret = {}
    url = ""
    raw_url = ""

    # clear old movie if passed 2 hours
    cm.tmp_movie_clear()

    if request.method == "POST":
        if "Url" not in request.form:
            status = state.ERR_BAD_REQ

            ret["result"] = rest_result
            ret["msg"] = state.get_error_message(status)
            ret["status"] = status
            return jsonify(ret)
        else:
            raw_url = request.form["Url"]

    elif request.method == "GET":
        if "Url" not in request.args:
            status = state.ERR_BAD_REQ

            ret["result"] = rest_result
            ret["msg"] = state.get_error_message(status)
            ret["status"] = status
            return jsonify(ret)
        else:
            raw_url = request.args.get("Url")

    # URL抽出
    tmp_group = re.search('(?:https?://)?(?P<host>.*?)(?:[:#?/@]|$)', raw_url)

    if tmp_group:
        host = tmp_group.group('host')
        if host == "www.youtube.com" or host == "youtu.be":
            url = raw_url

    # キャッシュ確認
    youtube_id = al.get_youtube_id(url)
    queue_path = queue_dir + str(youtube_id)
    pending_path = pending_dir + str(youtube_id)
    dl_queue_path = dl_queue_dir + str(youtube_id)
    if youtube_id is False:
        # 不正なurlの場合
        status = state.ERR_BAD_URL
    else:
        # 正常なurlの場合
        if SERVER_ERROR_STATE:
            ret["result"] = rest_result
            ret["msg"] = state.get_error_message(state.ERR_SERVICE_UNAVAILABLE)
            ret["status"] = state.ERR_SERVICE_UNAVAILABLE
            return jsonify(ret)

        # start analyze
        # 既にキューに登録されているか確認
        queued = os.path.exists(queue_path)
        if not queued:  # 既に解析中ではない場合、解析キューに登録
            cm.queue_append(queue_path)
            # キューが回ってきたか確認し、来たら解析実行
            while True:
                cm.watchdog(youtube_id, is_parent, 1800, state.TMP_QUEUE_TIMEOUT)
                rest_pending = cm.is_path_exists(pending_path)
                rest_queue = cm.is_path_due(queue_path)
                web_download = cm.is_path_exists(dl_queue_path)
                if not rest_pending and rest_queue and not web_download:
                    if cm.is_pending_download(15):  # check pending download
                        analyzer_path = f'python exec_analyze.py {url}'
                        cm.pending_append(pending_path)
                        subprocess.Popen(analyzer_path.split())
                        is_parent = True
                        break

                tm.sleep(1)

        while True:  # キューが消えるまで監視
            queued = os.path.exists(queue_path)
            if queued:
                if is_parent:
                    # 親ならばpendingを監視
                    cm.watchdog(youtube_id, is_parent, 300, state.TMP_ANALYZE_TIMEOUT)
                else:
                    # 子ならばqueueを監視
                    cm.watchdog(youtube_id, is_parent, 2160, state.TMP_QUEUE_TIMEOUT)
                tm.sleep(1)
                continue
            else:  # 解析が完了したら、そのキャッシュJSONを返す
                cache = cm.queue_cache_check(youtube_id)
                if cache:
                    title, time_line, time_line_enemy, time_data, total_damage, debuff_value, past_status = cache
                    rest_result = get_rest_result(title, time_line, time_line_enemy, time_data, total_damage, debuff_value)

                    status = past_status
                    break
                else:  # キャッシュ未生成の場合
                    # キャッシュを書き出してから解析キューから削除されるため、本来起こり得ないはずのエラー
                    status = state.TMP_UNEXPECTED
                    break

    ret["result"] = rest_result
    ret["msg"] = state.get_error_message(status)
    ret["status"] = status
    return jsonify(ret)


if __name__ == "__main__":
    app.run()
