#!/usr/bin/env python3

import os
import sys
import cv2
import dlib
import subprocess
import os
import requests
import time
import hashlib
import re
from datetime import datetime

from moviepy.editor import VideoFileClip

from typing import List
import platform
import signal
import shutil


def is_video_720p(file_path):
    clip = VideoFileClip(file_path)
    resolution = clip.size
    if os.path.splitext(file_path)[1].lower() != '.mp4':
        return False
    print(f"Video resolution: {resolution[0]}x{resolution[1]}")
    
    return resolution[0] <= 1280 and resolution[1] <= 720

def convert_to_720p(input_path):
    if is_video_720p(input_path):
        print("Video resolution is 720p or lower. No conversion needed.")
        return

    # 生成重命名后的文件名
    file_name, file_extension = os.path.splitext(os.path.basename(input_path))
    renamed_path = os.path.join(os.path.dirname(input_path), f"src_{file_name}{file_extension}")

    # 重命名原始文件
    os.rename(input_path, renamed_path)

    # 转换并保存为新文件（使用重新编码而非快速拷贝）
    output_path = os.path.join(os.path.dirname(renamed_path), f"{file_name}.mp4")
    ffmpeg_command = [
        'ffmpeg',
        '-y', 
        '-i', renamed_path,
        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
        output_path
    ]
    subprocess.run(ffmpeg_command)

    print(f"Video successfully converted to 720p. Saved at {output_path}")


def upload_file(url, file_path):
    chunk_size = 1024 * 1024  # 1MB
    total_chunks = -(-os.path.getsize(file_path) // chunk_size)  # 總分片數，無條件取整
    current_chunk = 0
    data = {'name': '', 'link': ''}
    fileSize = os.path.getsize(file_path)
    upFileName = str(time.time()) + str(fileSize) + file_path
    with open(file_path, 'rb') as f:
        while current_chunk < total_chunks:
            start = current_chunk * chunk_size
            end = min(start + chunk_size, os.path.getsize(file_path))
            chunk = f.read(end - start)
            
            files = {
                'file': (os.path.basename(file_path), chunk),
                'chunkNumber': (None, str(current_chunk + 1)),
                'totalChunks': (None, str(total_chunks)),
                'fileSize': (None, fileSize),
                'fileName': (None, upFileName)
            }
            
            response = requests.post(url, files=files)
            print(response.text)
            res_json = response.json()
            if res_json['status'] != 'success':
                print(f'Upload error: Chunk {current_chunk + 1} / {total_chunks}')
                return data
            
            current_chunk += 1
            data = res_json

        now = datetime.now()
        data['name'] = os.path.basename(file_path)
        data['hash'] =  now.strftime("%Y-%m-%d %H:%M:%S")  # 請替換為計算哈希值的方法
        print(f'文件大小：{os.path.getsize(file_path)}  {data["size"]}')
        # 調用捕獲視頻畫面並上傳縮略圖的函數，並將返回的數據更新到 data 對象中
        # tres = capture_video_frame_and_upload(file_path)
        # data['thumb'] = tres['thumb']
        
        print('Upload success!')
        return data



def download_file(url, filename):
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, 'wb') as file:
            file.write(response.content)
            print(f"File '{filename}' downloaded and saved successfully.")
    else:
        print(f"Error downloading file from {url}")

import requests


def callApi(name, data):
    try:
        #TODO 做簽名認證
        response = requests.post('http://192.3.153.102:3000/api/' + name, data)
        response_json = response.json()
        if response.status_code == 200:
            print('Request successful')
            return response_json
        else:
            print('Request failed')
            print(response_json.get('message', 'Unknown error'))
    except Exception as e:
        print('Error:', str(e))

def addLog(finish, state, log, process, total_frame = 0):
    callApi("workerUpdateTask", {'task_id':taskData['_id'], 'total_frame':total_frame,'finish':finish, 'state':state, 'log':log, 'process':process})

def delete_files(file_paths):
    for file_path in file_paths:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"文件 '{file_path}' 已被删除。")
        else:
            print(f"文件 '{file_path}' 不存在，无需删除。")

def detect_first_face_frame(input_video_filename):
    face_detector = dlib.get_frontal_face_detector()
    cap = cv2.VideoCapture(input_video_filename)

    min_x, min_y, max_x, max_y = float('inf'), float('inf'), 0, 0
    frame_skip_interval = 30
    frame_count = 0
    first_face_frame = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_skip_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # 使用 dlib 进行人脸检测
            faces = face_detector(gray)
            for face in faces:
                x, y, w, h = face.left(), face.top(), face.width(), face.height()
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x + w)
                max_y = max(max_y, y + h)
                if first_face_frame is None:
                    first_face_frame = frame_count
        frame_count += 1

    cap.release()
    return first_face_frame

def work():
    global taskData
    data = callApi("workerGetTask", {'type':'pre'})
    print(data)

  #  proc_media('media_filename', 'face_filename', 'out_file_path')
    if data["code"] != 0:
        print("Error: Code is not 0.")
        time.sleep(3)
    #    sys.exit(0)
        return
    try:
        delete_files(['face.png','media.gif','media.png','media.mp4','media_out.gif','media_out.mp4','media_out.jpg'])
        print(f"temp have been removed.")
    except Exception as e:
        print(f"Error deleting directory: {e}")

    taskData = data['data']

    media_file_url = ''
    face_file_url = ''
    if data['data']['media'] == False:
        return;
    if data['data']['face'] == False:
        return;

    try:
        media_file_url = data['data']['media']['file_url']
        face_file_url = data['data']['face']['file_url']
    except Exception as e:
        print(f"error get media_file_url: {e} {data}")
    
    media_filename = "media" + os.path.splitext(media_file_url)[1]
    face_filename = "face" + os.path.splitext(face_file_url)[1]
        
    download_file(media_file_url, media_filename)
    download_file(face_file_url, face_filename)

    extName = os.path.splitext(media_file_url)[1].lower()

    if media_filename.lower().endswith(('.m4v', '.mkv', '.avi', '.mov', '.webm', '.mpeg', '.mpg', '.wmv', '.flv', '.asf', '.3gp', '.3g2', '.ogg', '.vob', '.rmvb', '.ts', '.m2ts', '.divx', '.xvid', '.h264', '.avc', '.hevc', '.vp9', '.avchd')):
        
        convert_to_720p(media_filename)
        out_file_path = 'media.mp4'

        is_enhancement = int(taskData.get('is_enhancement', 0))
        reference_frame_number = str(taskData.get('reference_frame_number', 0))

        print('is_enhancement, reference_frame_number', is_enhancement, reference_frame_number);
        

        if not os.path.exists(out_file_path):
            print(f"找不到文件 {out_file_path}")
            
            return

        upload_video_res = upload_file('https://fakeface.io/upload.php?m=media', out_file_path)
        
        callApi("workerUpdateTask", {'task_id':taskData['_id'], 'media_url':upload_video_res, 'preprocessing':1, 'state':-1, 'finish':1})
        
        return

   
    addLog(1, 3, 'wrong file format', 100)

if __name__ == '__main__':
   # while True:
    work()
