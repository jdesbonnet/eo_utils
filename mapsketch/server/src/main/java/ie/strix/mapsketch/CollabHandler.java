package ie.strix.mapsketch;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.web.socket.*;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class CollabHandler extends TextWebSocketHandler {
  private final ObjectMapper mapper = new ObjectMapper();
  // room -> sessions
  private final Map<String, Set<WebSocketSession>> rooms = new ConcurrentHashMap<>();
  // session -> room
  private final Map<WebSocketSession, String> sessionRoom = new ConcurrentHashMap<>();

  @Override
  public void afterConnectionEstablished(WebSocketSession session) { /* wait for first message with room */ }

  @Override
  protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {

System.out.println("message received, message="+message);

    JsonNode root = mapper.readTree(message.getPayload());
    String room = root.has("room") ? root.get("room").asText() : "default";

    // on first message, register session in room
    sessionRoom.computeIfAbsent(session, s -> {
      rooms.computeIfAbsent(room, r -> ConcurrentHashMap.newKeySet()).add(session);
      return room;
    });

    // broadcast within the room only
    broadcast(room, message.getPayload());
  }

  private void broadcast(String room, String payload) {
System.out.print("broadcast message, message="+payload);
    Set<WebSocketSession> targets = rooms.getOrDefault(room, Collections.emptySet());
    for (WebSocketSession s : targets) {
      if (s.isOpen()) {
        try { s.sendMessage(new TextMessage(payload)); System.out.print("*");} catch (IOException ignored) {}
      }
    }
System.out.println("");
  }

  @Override
  public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
    String room = sessionRoom.remove(session);
    if (room != null) {
      Set<WebSocketSession> set = rooms.get(room);
      if (set != null) {
        set.remove(session);
        if (set.isEmpty()) rooms.remove(room);
      }
    }
  }
}

