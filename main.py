#!/usr/bin/env python3

import os
import sys
import cv2
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

import http.client
from urllib.parse import urlparse
from tqdm import tqdm


def convert_to_720p(input_path):
    clip = VideoFileClip(input_path)
    resolution = clip.size
    fps = clip.fps
    
    # 生成重命名后的文件名
    file_name, file_extension = os.path.splitext(os.path.basename(input_path))
    renamed_path = os.path.join(os.path.dirname(input_path), f"src_{file_name}{file_extension}")

    # 备份原始文件
    #os.rename(input_path, renamed_path)
    shutil.copy(input_path, renamed_path)

    # 转换并保存为新文件（使用重新编码而非快速拷贝）
    output_path = os.path.join(os.path.dirname(renamed_path), f"{file_name}.mp4")
    ffmpeg_command = [
        'ffmpeg',
        '-y', 
        '-i', renamed_path
    ]
    needPro = 0
    if resolution[0] > 720 or resolution[1] > 720:
        ffmpeg_command.append('-vf')
        ffmpeg_command.append('scale=trunc(iw/2)*2:trunc(ih/2)*2')
        needPro = 1
    elif resolution[0] > 1280 or resolution[1] > 1280:
        ffmpeg_command.append('-vf')
        ffmpeg_command.append('scale=trunc(iw/4)*2:trunc(ih/4)*2')
        needPro = 1
    if fps > 25:
        ffmpeg_command.append('-r')
        ffmpeg_command.append('25')
        needPro = 1
    if os.path.splitext(input_path)[1].lower() != '.mp4':
        needPro = 1

		#if: clip.duration > 120:
        
		#else:
		#	ffmpeg_command.append('-vf')
       # 	ffmpeg_command.append('scale=-1:720')
		#ffmpeg_command.append('-c:a')
        #ffmpeg_command.append('copy')
    #    needPro = 1
    ffmpeg_command.append(output_path)

    if needPro:
        print(ffmpeg_command)
        #os.remove(output_path)
        subprocess.run(ffmpeg_command)
        print(f"Video successfully converted. Saved at {output_path}")
    else:
        print(f"No need converted")

def add_watermark_to_image(input_path):
    """
    使用 FFmpeg 给图片添加水印
    """
    # 生成重命名后的文件名
    file_name, file_extension = os.path.splitext(os.path.basename(input_path))
    output_path = os.path.join(os.path.dirname(input_path), f"{file_name}{file_extension}")

    # 构建 FFmpeg 命令
    ffmpeg_command = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf",
        f"drawtext=text='':"
        f"x=w-tw-20:y=h-th-20:fontsize=24:"
        f"fontcolor=white@0.3:shadowx=2:shadowy=2:shadowcolor=black@0.3",
        output_path
    ]

    # 执行命令
    try:
        subprocess.run(ffmpeg_command, check=True)
        print(f"图片已添加水印，保存为: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"添加水印失败: {e}")

def calculate_md5(input_string):
    md5_hash = hashlib.md5(input_string.encode()).hexdigest()
    return md5_hash

def upload_file_to_s3(file_path, signed_url):
    """
    Uploads a file to a signed S3 URL with progress information using http.client.

    :param file_path: The path to the file to upload.
    :param signed_url: The signed URL to upload the file to.
    """
    file_size = os.path.getsize(file_path)
    url_parts = urlparse(signed_url)
    conn = http.client.HTTPSConnection(url_parts.netloc)
    
    with open(file_path, 'rb') as file, tqdm(total=file_size, unit='B', unit_scale=True, desc=file_path) as pbar:
        headers = {
            'Content-Type': 'application/octet-stream',
            'Content-Length': str(file_size),
        }

        conn.putrequest("PUT", url_parts.path + '?' + url_parts.query)
        for key, value in headers.items():
            conn.putheader(key, value)
        conn.endheaders()

        # Upload file in chunks
        chunk_size = 1024 * 1024  # 1MB
        while True:
            data = file.read(chunk_size)
            if not data:
                break
            conn.send(data)
            pbar.update(len(data))

    response = conn.getresponse()
    print(response.status, response.reason)
    if response.status == 200:
        print("File uploaded successfully")
        return True
    else:
        print("File upload failed")
        return False

def upload_file(file_path, ext=0):
    
    res = callApi("workerSignS3", {'filename': file_path})
    print(res)
    if res["code"] < 0:
        print('sign s3url error')
    upres = upload_file_to_s3(file_path, res["data"]["url"])
    if upres:
        return res["data"]["pubUrl"]
    return False

def upload_file_old(url, file_path):
    chunk_size = 1024 * 1024 * 2  # 1MB
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

def upload_image(upload_url, image_path):
    files = {'file': (image_path, open(image_path, 'rb'), 'image/jpeg')}
    try:
        response = requests.post(upload_url, files=files)
        response_json = response.json()  # 尝试解析JSON响应
        
        if response_json['status'] == 'success':
            print('Upload successful')
            return response_json
        else:
            print('Upload failed')
            print(response_json)
    except Exception as e:
        print('Error:', str(e))

def add_border(input_image_path, output_image_path):
    try:
        # 读取图片
        img = cv2.imread(input_image_path)
        
        # 检查是否成功读取图片
        if img is None:
            raise FileNotFoundError(f"Error: Unable to open image file {input_image_path}")
        
        # 获取图片的高度和宽度
        height, width = img.shape[:2]
        
        # 计算边框厚度
        border_thickness = min(height, width) // 4
        
        # 添加黑色边框
        img_with_border = cv2.copyMakeBorder(
            img,
            top=border_thickness,
            bottom=border_thickness,
            left=border_thickness,
            right=border_thickness,
            borderType=cv2.BORDER_CONSTANT,
            value=[0, 0, 0]  # 黑色
        )
        
        # 保存带有边框的图片
        cv2.imwrite(output_image_path, img_with_border)
        
        print(f"Successfully added border to {input_image_path} and saved to {output_image_path}")
    
    except Exception as e:
        print(f"An error occurred: {e}")

def generate_img_thumbnail(image_path, thumbnail_path, max_size=512):
    # 读取图片
    image = cv2.imread(image_path)
    
    if image is None:
        raise ValueError(f"Unable to read image from {image_path}")

    # 获取图片的宽和高
    height, width, _ = image.shape

    # 调整缩略图的大小
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        image = cv2.resize(image, (new_width, new_height))
    
    # 保存缩略图
    cv2.imwrite(thumbnail_path, image)
def generate_video_thumbnail(video_path, thumbnail_path, max_size=512):
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    
    if ret:
        # 获取视频帧的宽和高
        frame_height, frame_width, _ = frame.shape
        
        # 调整缩略图的大小
        if frame_width > max_size or frame_height > max_size:
            if frame_width > frame_height:
                new_width = max_size
                new_height = int(frame_height * (max_size / frame_width))
            else:
                new_height = max_size
                new_width = int(frame_width * (max_size / frame_height))
            frame = cv2.resize(frame, (new_width, new_height))
        
        # 保存缩略图
        cv2.imwrite(thumbnail_path, frame)
    
    cap.release()

def calculate_md5(input_string):
    md5_hash = hashlib.md5(input_string.encode()).hexdigest()
    return md5_hash


def callApi(name, data):
    try:
        #TODO 做簽名認證
        response = requests.post('https://api.fakeface.io/api/' + name, data, timeout=10)
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
def gif2mp4(gif, mp4):
    ffmpeg_command = [
        'ffmpeg',
        '-i', gif,
        '-c:v', 'libx264',  # 使用H.264编码器
        '-pix_fmt', 'yuv420p',  # 设置像素格式，通常需要
   #     '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',  # 将高度和宽度调整为2的倍数
        '-y',  # 强制覆盖
        mp4
    ]
    subprocess.run(ffmpeg_command)
  
    
def mp42gif(input_mp4_filename, output_gif_filename):
    ffmpeg_command = [
        'ffmpeg',
        '-y',  # 强制覆盖
        '-i', input_mp4_filename,
   #     '-vf', 'fps=10,scale=320:-1:flags=lanczos',  # 设置帧速率和尺寸等参数
        output_gif_filename
    ]
    subprocess.run(ffmpeg_command)

def proc_media(media_filename, face_filename, out_file_path, is_enhancement, reference_frame_number):
    print(media_filename, face_filename, out_file_path)
    #python run.py -o ./out.mp4 -s face.jpg -t media.mp4 --frame-processors face_swapper  --headless  --execution-providers coreml
    mode = 'cuda'
    if sys.argv[1] == 'cpu':
        mode = 'cpu'
    command = [
        'python',
        'run.py',
        '-s', face_filename, 
        '-t', media_filename,
        '-o', './' + out_file_path,
        '--execution-providers', mode, 
        '--headless',
        '--face-selector-mode', 'many',
        '--face-analyser-order', 'best-worst',
        '--output-video-encoder', 'libx264',
        '--face-mask-types','occlusion',
        #'--reference-frame-number', reference_frame_number,
        #'--reference-face-distance','1',
        '--face-detector-score','0.25',
        '--output-video-quality','70',
        '--frame-processors','face_swapper'
    ]
    if is_enhancement:
        command.append('face_enhancer')
        
    subprocess.run(command)
    return
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True  # 用于以文本模式获取输出
    )

    while True:
        output_line = process.stdout.readline()
        if not output_line and process.poll() is not None:
            break

        # 在这里解析输出并提取进度信息
        progress_match = re.search(r'Processing:\s+(\d+)%', output_line)
        if progress_match:
            progress_percentage = int(progress_match.group(1))
            print(f'Progress: {progress_percentage}%')

        # 如果你还想要其他输出，可以在这里处理

        time.sleep(1)

    process.stdout.close()
    process.wait() 


def delete_files(file_paths):
    for file_path in file_paths:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"文件 '{file_path}' 已被删除。")
        else:
            print(f"文件 '{file_path}' 不存在，无需删除。")
   
def work():
    global taskData
    mode = 'cuda'
    if sys.argv[1] == 'cpu':
        mode = 'cpu'
    term = sys.argv[2] if len(sys.argv) > 2 else 'cuda'
    data = callApi("workerGetTask", {'sc':sys.argv[3], 'mode':mode, 'term':term})
    print(data)

  #  proc_media('media_filename', 'face_filename', 'out_file_path')
    if data["code"] != 0:
        print("Error: Code is not 0.")
        time.sleep(3)
    #    sys.exit(0)
        return
    try:
        delete_files(['nsfw', 'face.png','media.gif','media.png','media.mp4','media_out.gif','media_out.mp4','media_out.jpg'])
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

    add_border(face_filename, face_filename)

    extName = os.path.splitext(media_file_url)[1].lower()

    is_enhancement = int(taskData.get('is_enhancement', 0))
    reference_frame_number = str(taskData.get('reference_frame_number', 0))

    nsfw = int(taskData.get('nsfw', 0))
    if nsfw == 1:
        open("nsfw", "w").close()

    if os.path.exists("nsfw"):
        print("文件 'nsfw' 存在。")
    else:
        print("文件 'nsfw' 不存在。")

    print('is_enhancement, reference_frame_number', is_enhancement, reference_frame_number);
        
    if media_filename.lower().endswith(('.mp4', '.m4v', '.mkv', '.avi', '.mov', '.webm', '.mpeg', '.mpg', '.wmv', '.flv', '.asf', '.3gp', '.3g2', '.ogg', '.vob', '.rmvb', '.ts', '.m2ts', '.divx', '.xvid', '.h264', '.avc', '.hevc', '.vp9', '.avchd')):
        
        convert_to_720p(media_filename)

        media_filename = 'media.mp4'
        
        out_file_path = 'media_out.mp4'
        proc_media(media_filename, face_filename, out_file_path, is_enhancement, reference_frame_number)
        thumb_file_path = 'thumb_media.jpg'
        generate_video_thumbnail(out_file_path, thumb_file_path)
        if not os.path.exists(out_file_path):
            print(f"找不到文件 {out_file_path}")
            addLog(1, -1, 'Processing failed', 99)
            return
        upload_video_url = upload_file(out_file_path)
        upload_image_url = upload_file(thumb_file_path)
        print('Upload result:', upload_video_url, upload_image_url)
        now = datetime.now()
        api_res = callApi("wokerAddMedia", {'user_id':data['data']['user_id'], 'media_id':data['data']['finish_media_id'], 'file_url':upload_video_url, 'thumb_url':upload_image_url, 'file_hash':now.strftime("%Y-%m-%d %H:%M:%S")})
        print('Api result:', api_res)
        addLog(1, 3, 'finish', 100)
        return

    if media_filename.lower().endswith(('.gif')):
        out_file_path = 'media_out.mp4'
        print('文件后缀：', extName)
        gif2mp4('media.gif', 'media.mp4')
        proc_media('media.mp4', face_filename, out_file_path, is_enhancement,reference_frame_number)
        thumb_file_path = 'thumb_media.jpg'
        generate_video_thumbnail(out_file_path, thumb_file_path)
        mp42gif('media_out.mp4', 'media_out.gif')
        out_file_path = 'media_out.gif'
        if not os.path.exists(out_file_path):
            print(f"找不到文件 {out_file_path}")
            addLog(1, -1, 'Processing failed', 99)
            return
        upload_video_url = upload_file(out_file_path)
        upload_image_url = upload_file(thumb_file_path)
        print('Upload result:', upload_video_url, upload_image_url)
        now = datetime.now()
        api_res = callApi("wokerAddMedia", {'user_id':data['data']['user_id'], 'media_id':data['data']['finish_media_id'], 'file_url':upload_video_url, 'thumb_url':upload_image_url, 'file_hash':now.strftime("%Y-%m-%d %H:%M:%S")})
        print('Api result:', api_res)
        addLog(1, 3, 'finish', 100)
        return
    if media_filename.lower().endswith(('.jpg')):
        out_file_path = 'media_out.jpg'
        real_out_file_path = 'media_out.jpg'
        add_watermark_to_image(media_filename)
        proc_media(media_filename, face_filename, out_file_path, 1,reference_frame_number)
        thumb_file_path = 'thumb_media.jpg'
        generate_img_thumbnail(out_file_path, thumb_file_path)
        if not os.path.exists(out_file_path):
            print(f"找不到文件 {out_file_path}")
            addLog(1, -1, 'Processing failed', 99)
            return
        upload_file_url = upload_file(out_file_path)
        upload_image_url = upload_file(thumb_file_path)
        now = datetime.now()
        api_res = callApi("wokerAddMedia", {'user_id':data['data']['user_id'], 'media_id':data['data']['finish_media_id'], 'file_url':upload_file_url, 'thumb_url':upload_image_url, 'file_hash':now.strftime("%Y-%m-%d %H:%M:%S") })
        print('Api result:', api_res)
        addLog(1, 3, 'finish', 100)
        return
    addLog(1, 3, 'wrong file format', 100)

if __name__ == '__main__':
   # while True:
    work()
