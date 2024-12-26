from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import uvicorn
from typing import List, Dict
import asyncio
import json
import os
from datetime import datetime  # 시간 기록을 위해 추가

app = FastAPI()

# 그림 데이터를 저장할 클래스
class PixelCanvas:
    def __init__(self):
        self.pixels: List[Dict] = []
        self.load_pixels()  # 초기화할 때 저장된 데이터 불러오기

    def add_pixel(self, pixel_data: dict):
        # 지우개인 경우 해당 위치의 픽셀 제거
        if pixel_data.get('color') == 'erase':
            self.pixels = [p for p in self.pixels if 
                         not (p['x'] == pixel_data['x'] and p['y'] == pixel_data['y'])]
        else:
            self.pixels.append(pixel_data)
        self.save_pixels()  # 픽셀 추가/삭제할 때마다 저장

    def save_pixels(self):
        try:
            with open('pixel_data.json', 'w') as f:
                json.dump(self.pixels, f)
        except Exception as e:
            print(f"픽셀 데이터 저장 중 오류 발생: {e}")

    def load_pixels(self):
        try:
            if os.path.exists('pixel_data.json'):
                with open('pixel_data.json', 'r') as f:
                    self.pixels = json.load(f)
        except Exception as e:
            print(f"픽셀 데이터 로드 중 오류 발생: {e}")
            self.pixels = []

    # 캔버스 초기화 메서드 추가
    def clear_canvas(self):
        self.pixels = []
        self.save_pixels()  # 빈 상태를 저장
        return {"type": "clear_canvas"}  # 클리어 메시지

canvas = PixelCanvas()

# 웹소켓 연결을 관리하는 클래스
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_numbers: Dict[str, int] = {}  # IP 주소를 키로 사용
        self.current_number = 0
        self.websocket_to_ip: Dict[WebSocket, str] = {}  # WebSocket과 IP 매핑
        self.banned_words = ['시발', '병신','섹스','ㅅㅂ','sex','tlqkf','qudtls','ㅂㅅ','ㅄ','ㅅㅅ','김도현','고대욱','오광주','또라이','ㄸㄹㅇ','글로브','글','커먼','common']  # 금지어 리스트 추가
        self.chat_log_file = "chat_log.txt"  # 채팅 로그 파일

    def get_client_ip(self, websocket: WebSocket) -> str:
        client_host = websocket.client.host
        return client_host

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
        # IP 주소 가져오기
        client_ip = self.get_client_ip(websocket)
        self.websocket_to_ip[websocket] = client_ip
        
        # IP 주소에 대한 번호가 없으면 새로 할당
        if client_ip not in self.user_numbers:
            self.current_number += 1
            self.user_numbers[client_ip] = self.current_number
        
        # 기존 그림 데이터 전송
        for pixel in canvas.pixels:
            await websocket.send_json(pixel)
        await self.broadcast_user_count()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.websocket_to_ip:
            # IP 주소는 유지하고 웹소켓 연결 정보만 삭제
            del self.websocket_to_ip[websocket]
        self.active_connections.remove(websocket)
        asyncio.create_task(self.broadcast_user_count())

    def log_chat(self, ip: str, message: str):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{current_time}] IP: {ip} | Message: {message}\n"
        
        # 로그 파일에 기록
        with open(self.chat_log_file, "a", encoding="utf-8") as f:
            f.write(log_message)
        
        # 터미널에도 출력
        print(log_message, end="")

    async def broadcast(self, message: dict, sender: WebSocket = None):
        if sender and message.get("type") == "chat":
            chat_content = message.get("message", "")
            
            # 금지어 체크
            if any(word in chat_content for word in self.banned_words):
                warning = {
                    "type": "chat",
                    "message": "부적절한 단어가 포함되어 있어 메시지가 전송되지 않았습니다.",
                    "username": "시스템"
                }
                await sender.send_json(warning)
                return

            client_ip = self.websocket_to_ip.get(sender)
            if client_ip:
                user_number = self.user_numbers.get(client_ip)
                message["username"] = f"익명{user_number}"
                # 채팅 로그 기록
                self.log_chat(client_ip, chat_content)

        for connection in self.active_connections:
            await connection.send_json(message)

    async def broadcast_user_count(self):
        count_message = {"type": "user_count", "count": len(self.active_connections)}
        for connection in self.active_connections:
            await connection.send_json(count_message)

manager = ConnectionManager()

# 웹소켓 엔드포인트
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "chat":  # 채팅 메시지 처리
                await manager.broadcast(data, websocket)
            else:  # 픽셀 데이터 처리
                canvas.add_pixel(data)
                await manager.broadcast(data)
    except:
        manager.disconnect(websocket)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="steam/static"), name="static")

# 루트 경로를 index.html로 직접 리다이렉트
@app.get("/")
async def read_root():
    return RedirectResponse("/static/index.html")

# 관리자 명령어 처리를 위한 새로운 엔드포인트 추가
@app.post("/admin/clear")
async def clear_canvas(request: Request):
    # 실제 운영 환경에서는 보안을 위해 적절한 인증 절차를 추가해야 합니다
    admin_token = request.headers.get("Authorization")
    if admin_token != "your_secret_token":  # 실제 환경에서는 안전한 토큰을 사용하세요
        return {"error": "Unauthorized"}
    
    clear_message = canvas.clear_canvas()
    await manager.broadcast(clear_message)  # 모든 클라이언트에게 초기화 알림
    return {"message": "Canvas cleared successfully"}

if __name__ == "__main__":
    # 환경 변수에서 HOST와 PORT 가져오기 (기본값 설정)
    import socket                      # 네트워크 기능
    hostname = socket.gethostname()
    HOST = socket.gethostbyname(hostname)
    PORT = 8080
    
    # uvicorn 서버 실행 (자동 재시작 활성화)
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)