import { Component, OnInit, OnDestroy } from '@angular/core';
import { Subject, takeUntil, interval } from 'rxjs';
import { NotificationService } from '../../services/notification.service';
import { WebSocketService } from '../../services/websocket.service';
import { AuthService } from '../../services/auth.service';

interface DashboardStats {
  totalNotifications: number;
  sentToday: number;
  deliveredToday: number;
  failedToday: number;
  successRate: number;
  channelBreakdown: {
    email: number;
    sms: number;
    push: number;
    whatsapp: number;
  };
}

interface RecentNotification {
  id: string;
  channel: string;
  recipient: string;
  status: string;
  created_at: string;
  subject?: string;
}

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css']
})
export class DashboardComponent implements OnInit, OnDestroy {
  private destroy$ = new Subject<void>();
  
  stats: DashboardStats = {
    totalNotifications: 0,
    sentToday: 0,
    deliveredToday: 0,
    failedToday: 0,
    successRate: 0,
    channelBreakdown: {
      email: 0,
      sms: 0,
      push: 0,
      whatsapp: 0
    }
  };
  
  recentNotifications: RecentNotification[] = [];
  campaigns: any[] = [];
  templates: any[] = [];
  
  isLoading = true;
  isConnected = false;
  
  constructor(
    private notificationService: NotificationService,
    private websocketService: WebSocketService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    this.loadDashboardData();
    this.setupWebSocketConnection();
    this.setupAutoRefresh();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    this.websocketService.disconnectAll();
  }

  private loadDashboardData(): void {
    this.isLoading = true;
    
    // Load recent notifications
    this.notificationService.getNotifications({ limit: 10 })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.recentNotifications = response.results || [];
          this.updateStatsFromNotifications();
          this.isLoading = false;
        },
        error: (error) => {
          console.error('Error loading notifications:', error);
          this.isLoading = false;
        }
      });

    // Load campaigns
    this.notificationService.getCampaigns({ limit: 5 })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (response) => {
          this.campaigns = response.results || [];
        },
        error: (error) => {
          console.error('Error loading campaigns:', error);
        }
      });
  }

  private updateStatsFromNotifications(): void {
    this.stats.totalNotifications = this.recentNotifications.length;
    this.stats.sentToday = this.recentNotifications.filter(n => n.status === 'sent').length;
    this.stats.deliveredToday = this.recentNotifications.filter(n => n.status === 'delivered').length;
    this.stats.failedToday = this.recentNotifications.filter(n => n.status === 'failed').length;
    
    // Calculate channel breakdown
    this.stats.channelBreakdown = {
      email: this.recentNotifications.filter(n => n.channel === 'email').length,
      sms: this.recentNotifications.filter(n => n.channel === 'sms').length,
      push: this.recentNotifications.filter(n => n.channel === 'push').length,
      whatsapp: this.recentNotifications.filter(n => n.channel === 'whatsapp').length
    };
    
    if (this.stats.sentToday > 0) {
      this.stats.successRate = (this.stats.deliveredToday / this.stats.sentToday) * 100;
    }
  }

  private setupWebSocketConnection(): void {
    this.websocketService.getDashboardConnectionStatus()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (connected) => {
          this.isConnected = connected;
        }
      });

    this.websocketService.connectToNotifications()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (update) => {
          this.handleNotificationUpdate(update);
        }
      });
  }

  private setupAutoRefresh(): void {
    interval(30000)
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        this.loadDashboardData();
      });
  }

  private handleNotificationUpdate(update: any): void {
    const notificationIndex = this.recentNotifications.findIndex(
      n => n.id === update.notification_id
    );
    
    if (notificationIndex >= 0) {
      this.recentNotifications[notificationIndex].status = update.status;
      this.updateStatsFromNotifications();
    }
  }

  getStatusColor(status: string): string {
    switch (status) {
      case 'delivered': return 'text-green-600';
      case 'sent': return 'text-blue-600';
      case 'failed': return 'text-red-600';
      case 'pending': return 'text-yellow-600';
      case 'processing': return 'text-purple-600';
      default: return 'text-gray-600';
    }
  }

  getChannelIcon(channel: string): string {
    switch (channel) {
      case 'email': return '📧';
      case 'sms': return '📱';
      case 'push': return '🔔';
      case 'whatsapp': return '💬';
      default: return '📨';
    }
  }

  sendQuickNotification(): void {
    console.log('Send quick notification');
  }

  createCampaign(): void {
    console.log('Create new campaign');
  }

  viewAnalytics(): void {
    console.log('View analytics');
  }
}