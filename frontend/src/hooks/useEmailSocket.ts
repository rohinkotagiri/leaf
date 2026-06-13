import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

interface WebSocketMessage {
  type: string;
  email_id?: string;
  [key: string]: any;
}

export function useEmailSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);

  useEffect(() => {
    function connect() {
      if (socketRef.current) return;

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      // Fallback to localhost:8000 if running on vite dev port 5173
      const wsHost = window.location.port === '5173' ? 'localhost:8000' : window.location.host;
      const wsUrl = `${wsProtocol}//${wsHost}/ws`;

      console.log(`Connecting to WebSocket: ${wsUrl}`);
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        console.log('WebSocket connection established');
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
      };

      socket.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          console.log('WebSocket message received:', message);

          if (message.type === 'analysis_complete' && message.email_id) {
            console.log(`Email analysis completed for ${message.email_id}. Invalidating queries...`);
            
            // Invalidate the main emails listing queries
            queryClient.invalidateQueries({ queryKey: ['emails'] });
            
            // Invalidate specific email details
            queryClient.invalidateQueries({ queryKey: ['email', message.email_id] });
            queryClient.invalidateQueries({ queryKey: ['email-thread', message.email_id] });

            // Dispatch custom event for inline notifications/animations
            const customEvent = new CustomEvent('releaf_analysis_complete', {
              detail: { emailId: message.email_id },
            });
            window.dispatchEvent(customEvent);
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message data:', err);
        }
      };

      socket.onclose = (event) => {
        console.log('WebSocket connection closed:', event.reason);
        setIsConnected(false);
        socketRef.current = null;

        // Exponential backoff reconnect
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
        reconnectAttemptsRef.current += 1;
        console.log(`Attempting reconnect in ${delay}ms...`);

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      };

      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        socket.close();
      };
    }

    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        // Remove close handler to prevent reconnecting on cleanup
        socketRef.current.onclose = null;
        socketRef.current.close();
      }
    };
  }, [queryClient]);

  // Expose ping function if needed for keep-alive
  const ping = () => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send('ping');
    }
  };

  return { isConnected, ping };
}
