import { Injectable, OnDestroy } from '@angular/core';
import { Observable, Subject, BehaviorSubject } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export interface WebSocketMessage {
  type: string;
  data: any;
  timestamp: Date;
}

export interface NotificationUpdate {
  notification_id: string;
  status: string;
  message?: string;
  error?: string;
}

export interface CampaignUpdate {
  campaign_id: string;
  status: string;
  metrics?: any;
  message?: string;
}

@Injectable({
  providedIn: 'root'
})
export class WebSocketService implements OnDestroy {
  private wsUrl = environment.wsUrl;
  private reconnectInterval = 5000; // 5 seconds
  private maxReconnectAttempts = 5;

  // WebSocket connections
  private notificationSocket: WebSocket | null = null;
  private campaignSocket: WebSocket | null = null;
  private dashboardSocket: WebSocket | null = null;

  // Connection status
  private notificationConnected$ = new BehaviorSubject<boolean>(false);
  private campaignConnected$ = new BehaviorSubject<boolean>(false);
  private dashboardConnected$ = new BehaviorSubject<boolean>(false);

  // Message subjects
  private notificationMessages$ = new Subject<NotificationUpdate>();
  private campaignMessages$ = new Subject<CampaignUpdate>();
  private dashboardMessages$ = new Subject<any>();

  // Reconnection tracking
  private notificationReconnectAttempts = 0;
  private campaignReconnectAttempts = 0;
  private dashboardReconnectAttempts = 0;

  constructor(private authService: AuthService) {}

  ngOnDestroy() {
    this.disconnectAll();
  }

  /**
   * Connect to notification updates WebSocket
   */
  connectToNotifications(): Observable<NotificationUpdate> {
    if (!this.notificationSocket || this.notificationSocket.readyState === WebSocket.CLOSED) {
      this.createNotificationConnection();
    }
    return this.notificationMessages$.asObservable();
  }

  /**
   * Connect to campaign updates WebSocket
   */
  connectToCampaigns(): Observable<CampaignUpdate> {
    if (!this.campaignSocket || this.campaignSocket.readyState === WebSocket.CLOSED) {
      this.createCampaignConnection();
    }
    return this.campaignMessages$.asObservable();
  }

  /**
   * Connect to dashboard updates WebSocket
   */
  connectToDashboard(): Observable<any> {
    if (!this.dashboardSocket || this.dashboardSocket.readyState === WebSocket.CLOSED) {
      this.createDashboardConnection();
    }
    return this.dashboardMessages$.asObservable();
  }

  /**
   * Get notification connection status
   */
  getNotificationConnectionStatus(): Observable<boolean> {
    return this.notificationConnected$.asObservable();
  }

  /**
   * Get campaign connection status
   */
  getCampaignConnectionStatus(): Observable<boolean> {
    return this.campaignConnected$.asObservable();
  }

  /**
   * Get dashboard connection status
   */
  getDashboardConnectionStatus(): Observable<boolean> {
    return this.dashboardConnected$.asObservable();
  }

  /**
   * Disconnect from notifications WebSocket
   */
  disconnectFromNotifications(): void {
    if (this.notificationSocket) {
      this.notificationSocket.close();
      this.notificationSocket = null;
      this.notificationConnected$.next(false);
    }
  }

  /**
   * Disconnect from campaigns WebSocket
   */
  disconnectFromCampaigns(): void {
    if (this.campaignSocket) {
      this.campaignSocket.close();
      this.campaignSocket = null;
      this.campaignConnected$.next(false);
    }
  }

  /**
   * Disconnect from dashboard WebSocket
   */
  disconnectFromDashboard(): void {
    if (this.dashboardSocket) {
      this.dashboardSocket.close();
      this.dashboardSocket = null;
      this.dashboardConnected$.next(false);
    }
  }

  /**
   * Disconnect all WebSocket connections
   */
  disconnectAll(): void {
    this.disconnectFromNotifications();
    this.disconnectFromCampaigns();
    this.disconnectFromDashboard();
  }

  // Private methods

  private createNotificationConnection(): void {
    const user = this.authService.getCurrentUser();
    if (!user) {
      console.error('Cannot connect to WebSocket: User not authenticated');
      return;
    }

    const token = this.authService.getAccessToken();
    const url = `${this.wsUrl}/notifications/${user.id}/?token=${token}`;

    try {
      this.notificationSocket = new WebSocket(url);

      this.notificationSocket.onopen = () => {
        console.log('Notification WebSocket connected');
        this.notificationConnected$.next(true);
        this.notificationReconnectAttempts = 0;
      };

      this.notificationSocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.notificationMessages$.next(data);
        } catch (error) {
          console.error('Error parsing notification WebSocket message:', error);
        }
      };

      this.notificationSocket.onclose = (event) => {
        console.log('Notification WebSocket disconnected:', event.code, event.reason);
        this.notificationConnected$.next(false);
        this.handleNotificationReconnect();
      };

      this.notificationSocket.onerror = (error) => {
        console.error('Notification WebSocket error:', error);
        this.notificationConnected$.next(false);
      };

    } catch (error) {
      console.error('Error creating notification WebSocket connection:', error);
    }
  }

  private createCampaignConnection(): void {
    const user = this.authService.getCurrentUser();
    if (!user) {
      console.error('Cannot connect to WebSocket: User not authenticated');
      return;
    }

    const token = this.authService.getAccessToken();
    const url = `${this.wsUrl}/campaigns/${user.id}/?token=${token}`;

    try {
      this.campaignSocket = new WebSocket(url);

      this.campaignSocket.onopen = () => {
        console.log('Campaign WebSocket connected');
        this.campaignConnected$.next(true);
        this.campaignReconnectAttempts = 0;
      };

      this.campaignSocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.campaignMessages$.next(data);
        } catch (error) {
          console.error('Error parsing campaign WebSocket message:', error);
        }
      };

      this.campaignSocket.onclose = (event) => {
        console.log('Campaign WebSocket disconnected:', event.code, event.reason);
        this.campaignConnected$.next(false);
        this.handleCampaignReconnect();
      };

      this.campaignSocket.onerror = (error) => {
        console.error('Campaign WebSocket error:', error);
        this.campaignConnected$.next(false);
      };

    } catch (error) {
      console.error('Error creating campaign WebSocket connection:', error);
    }
  }

  private createDashboardConnection(): void {
    const user = this.authService.getCurrentUser();
    if (!user) {
      console.error('Cannot connect to WebSocket: User not authenticated');
      return;
    }

    const token = this.authService.getAccessToken();
    const url = `${this.wsUrl}/dashboard/${user.id}/?token=${token}`;

    try {
      this.dashboardSocket = new WebSocket(url);

      this.dashboardSocket.onopen = () => {
        console.log('Dashboard WebSocket connected');
        this.dashboardConnected$.next(true);
        this.dashboardReconnectAttempts = 0;
      };

      this.dashboardSocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.dashboardMessages$.next(data);
        } catch (error) {
          console.error('Error parsing dashboard WebSocket message:', error);
        }
      };

      this.dashboardSocket.onclose = (event) => {
        console.log('Dashboard WebSocket disconnected:', event.code, event.reason);
        this.dashboardConnected$.next(false);
        this.handleDashboardReconnect();
      };

      this.dashboardSocket.onerror = (error) => {
        console.error('Dashboard WebSocket error:', error);
        this.dashboardConnected$.next(false);
      };

    } catch (error) {
      console.error('Error creating dashboard WebSocket connection:', error);
    }
  }

  private handleNotificationReconnect(): void {
    if (this.notificationReconnectAttempts < this.maxReconnectAttempts) {
      this.notificationReconnectAttempts++;
      console.log(`Attempting to reconnect to notification WebSocket (${this.notificationReconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        if (this.authService.isAuthenticatedValue) {
          this.createNotificationConnection();
        }
      }, this.reconnectInterval);
    } else {
      console.error('Max reconnection attempts reached for notification WebSocket');
    }
  }

  private handleCampaignReconnect(): void {
    if (this.campaignReconnectAttempts < this.maxReconnectAttempts) {
      this.campaignReconnectAttempts++;
      console.log(`Attempting to reconnect to campaign WebSocket (${this.campaignReconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        if (this.authService.isAuthenticatedValue) {
          this.createCampaignConnection();
        }
      }, this.reconnectInterval);
    } else {
      console.error('Max reconnection attempts reached for campaign WebSocket');
    }
  }

  private handleDashboardReconnect(): void {
    if (this.dashboardReconnectAttempts < this.maxReconnectAttempts) {
      this.dashboardReconnectAttempts++;
      console.log(`Attempting to reconnect to dashboard WebSocket (${this.dashboardReconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        if (this.authService.isAuthenticatedValue) {
          this.createDashboardConnection();
        }
      }, this.reconnectInterval);
    } else {
      console.error('Max reconnection attempts reached for dashboard WebSocket');
    }
  }
}
