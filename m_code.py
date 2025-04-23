import asyncio
import json
import websockets
import math
import re
import pygame
import random 

MAX_SAFE_ALTITUDE = 3
MAX_SPEED = 5
MIN_ALTITUDE = 1
TILT_CRITICAL = math.radians(45)
LOW_BATTERY = 20
CRITICAL_BATTERY = 10
# SAFE_ALT_FOR_GREEN = 3
# SAFE_ALT_FOR_YELLOW = 2
SAFE_ALT_FOR_RED = 2.8

#fOR visualization i have taken help from CHATGPT
#i had very less knowledge about pygame
class DroneVisualizer:
    def __init__(self, width=800, height=500):
        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Drone Flight Visualizer")
        self.font = pygame.font.SysFont("Arial", 18)
        self.clock = pygame.time.Clock()
        self.width = width
        self.height = height

        # Graphing
        self.altitude_history = []
        self.max_history = 100
        self.graph_height = 100
        self.graph_top = self.height - self.graph_height - 10

    def draw(self, telemetry):
        self.screen.fill((10, 10, 20))

        x_pos = int(self.width // 2 + telemetry["x"] / 1000)
        y_pos = int(self.height - telemetry["y"] * 10 - self.graph_height)

        pygame.draw.circle(self.screen, (0, 255, 0), (x_pos, y_pos), 10)

        lines = [
            f"X: {telemetry['x']:.1f}",
            f"Y (Alt): {telemetry['y']:.1f}",
            f"Battery: {telemetry['battery']:.1f}%",
            f"Sensor: {telemetry['sensor']}",
            f"Wind: {telemetry['wind']:.1f}",
            f"Dust: {telemetry['dust']:.1f}",
            f"Tilt: {self.get_tilt(telemetry):.2f}",
        ]
        for i, line in enumerate(lines):
            text = self.font.render(line, True, (255, 255, 255))
            self.screen.blit(text, (10, 10 + i * 20))

        self.altitude_history.append(telemetry["y"])
        if len(self.altitude_history) > self.max_history:
            self.altitude_history.pop(0)
        self.draw_altitude_graph()

        pygame.display.flip()
        self.clock.tick(30)

    def draw_altitude_graph(self):
        if len(self.altitude_history) < 2:
            return

        graph_width = self.width
        points = self.altitude_history[-self.max_history:]
        max_alt = max(max(points), 1)
        min_alt = min(points)

        # Axis
        pygame.draw.line(self.screen, (150, 150, 150), (0, self.graph_top), (self.width, self.graph_top))
        pygame.draw.line(self.screen, (150, 150, 150), (0, self.graph_top), (0, self.graph_top + self.graph_height))

        for i in range(5):
            alt = min_alt + (max_alt - min_alt) * (i / 4)
            label = self.font.render(f"{alt:.1f}", True, (200, 200, 200))
            y_pos = self.graph_top + self.graph_height - int((alt - min_alt) / (max_alt - min_alt + 0.1) * self.graph_height)
            self.screen.blit(label, (5, y_pos - 10))

        scaled_points = [
            (
                int(i * (graph_width / self.max_history)),
                int(self.graph_top + self.graph_height - ((y - min_alt) / (max_alt - min_alt + 0.1)) * self.graph_height)
            )
            for i, y in enumerate(points)
        ]

        if len(scaled_points) > 1:
            pygame.draw.lines(self.screen, (255, 255, 0), False, scaled_points, 2)

        label = self.font.render("Altitude Graph (Recent)", True, (255, 255, 255))
        self.screen.blit(label, (10, self.graph_top - 20))

    def get_tilt(self, telemetry):
        gx, gy, gz = telemetry["gyroscope"]
        return (gx**2 + gy**2 + gz**2) ** 0.5

    def check_quit(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return True
        return False


# === Drone Client ===
async def drone_client():
    uri = "ws://localhost:8765"
    visualizer = DroneVisualizer()
    step = 0

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                print("Connected to Drone Simulator")
                starter_command = {"speed": 0, "altitude": 0, "movement": "fwd"}
                await websocket.send(json.dumps(starter_command))
                while True:
                    response = await websocket.recv()
                    data = json.loads(response)

                    if data.get("status") == "crashed":
                        print(" Drone crashed!")
                        if "metrics" in data:
                            print(" Flight Summary:", data["metrics"])
                        return

                    if "telemetry" not in data:
                        continue

                    telemetry = parse_telemetry(data["telemetry"])
                    if not telemetry:
                        print("No telemetry, skipping...")
                        continue

                    visualizer.draw(telemetry)
                    if visualizer.check_quit():
                        return

                    command = decide_next_move(telemetry)

                    await websocket.send(json.dumps(command))
                    await asyncio.sleep(1)

        except websockets.exceptions.ConnectionClosed:
            print("🔁 Connection closed. Reconnecting...")
            await asyncio.sleep(2)


# === Helpers ===
def parse_telemetry(telemetry_str):
    pattern = (
        r"X-(?P<x>-?\d+(\.\d+)?)"
        r"-Y-(?P<y>-?\d+(\.\d+)?)"
        r"-BAT-(?P<battery>-?\d+(\.\d+)?)"
        r"-GYR-\[\s*(?P<gx>-?\d+(\.\d+)?),\s*(?P<gy>-?\d+(\.\d+)?),\s*(?P<gz>-?\d+(\.\d+)?)\s*\]"
        r"-WIND-(?P<wind>-?\d+(\.\d+)?)"
        r"-DUST-(?P<dust>-?\d+(\.\d+)?)"
        r"-SENS-(?P<sensor>[A-Z]+)"
    )
    match = re.match(pattern, telemetry_str)
    if not match:
        print(f"❌ Failed to parse telemetry string: {telemetry_str}")
        return {}
    return {
        "x": float(match.group("x")),
        "y": float(match.group("y")),
        "battery": float(match.group("battery")),
        "gyroscope": (
            float(match.group("gx")),
            float(match.group("gy")),
            float(match.group("gz")),
        ),
        "wind": float(match.group("wind")),
        "dust": float(match.group("dust")),
        "sensor": match.group("sensor"),
    }

def decide_next_move(telemetry):
    y = telemetry["y"]
    battery = telemetry["battery"]
    sensor = telemetry["sensor"]
    wind = telemetry["wind"]
    dust = telemetry["dust"]
    gx, gy, gz = telemetry["gyroscope"]
    tilt = math.sqrt(gx**2 + gy**2 + gz**2)
    x = telemetry["x"]


    wind2 = wind
    dust2 = dust

    if battery <= CRITICAL_BATTERY:
        return {"speed": 5, "altitude": 1, "movement": "fwd"}

    if tilt > TILT_CRITICAL:
        return {"speed": 0, "altitude": -1 if y > 1 else 0, "movement": "fwd"}

    if sensor == "RED" and y >= SAFE_ALT_FOR_RED:
        
        return {"speed": 2, "altitude": -1, "movement": "fwd"}

    if sensor == "YELLOW" and y > 100:
        return {"speed": 3, "altitude": -2, "movement": "fwd"}

    if wind > 60 or dust > 60:
        print("Severe wind/dust staying in place.")
        if (wind - wind2) >= 20 or (dust - dust2) >= 20:
            return {"speed": 0, "altitude": 0, "movement": "rev"}  
        else:
            return {"speed": 1, "altitude": 1, "movement": "fwd"}  

    if wind > 40 or dust > 40:
        alt = 1 if (x % 2 == 0) else -1
        return {"speed": 2, "altitude": alt, "movement": "fwd"}  

    command = {"speed": 5, "altitude": 2, "movement": "fwd"}

    if battery < LOW_BATTERY:
        command["speed"] = min(command["speed"], 2)

    if sensor == "GREEN" and 2.0 < y < 18 and tilt < 0.25 and battery > 35 and wind < 30 and dust < 30:
        command = {"speed": 4, "altitude": 2, "movement": "fwd"}

    if sensor == "YELLOW":
        alt = 0 if (x % 2 == 0) else 1
        return {"speed": 1, "altitude": alt, "movement": "fwd"}

    if sensor == "RED":
        command["altitude"] = min(command["altitude"], 2)

    if x >= 1000:
        return {"speed": 0, "altitude": 0, "movement": "rev"}

    return command




if __name__ == "__main__":
    asyncio.run(drone_client())

