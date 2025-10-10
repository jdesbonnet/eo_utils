package ie.strix.mapsketch;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.*;

@Configuration
@EnableWebSocket
public class CollabWebSocketConfig implements WebSocketConfigurer {
  private final CollabHandler handler = new CollabHandler();

  @Override
  public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
    registry.addHandler(handler, "/ws")
            .setAllowedOriginPatterns("*"); // allow from anywhere for now
  }
}

