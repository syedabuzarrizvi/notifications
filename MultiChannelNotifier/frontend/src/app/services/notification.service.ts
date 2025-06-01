import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService, ApiResponse } from './api.service';
import { Notification, NotificationRequest, NotificationScheduleRequest, BulkNotificationRequest } from '../shared/models/notification.model';

export interface NotificationStats {
  total_notifications: number;
  today_notifications: number;
  week_notifications: number;
  month_notifications: number;
  status_breakdown: { [key: string]: number };
  channel_breakdown: { [key: string]: number };
  success_rate: {
    total: number;
    sent: number;
    delivered: number;
    failed: number;
    sent_percentage: number;
    delivered_percentage: number;
    failed_percentage: number;
  };
}

export interface Provider {
  id: string;
  name: string;
  channel: string;
  is_active: boolean;
  rate_limit_per_minute: number;
  rate_limit_per_hour: number;
  priority: number;
}

@Injectable({
  providedIn: 'root'
})
export class NotificationService {
  private baseEndpoint = '/notifications';

  constructor(private apiService: ApiService) {}

  /**
   * Send immediate notification
   */
  sendNotification(request: NotificationRequest): Observable<{ message: string; notification: Notification }> {
    return this.apiService.post(`${this.baseEndpoint}/send/`, request);
  }

  /**
   * Schedule notification
   */
  scheduleNotification(request: NotificationScheduleRequest): Observable<{ message: string; notification: Notification }> {
    return this.apiService.post(`${this.baseEndpoint}/schedule/`, request);
  }

  /**
   * Send bulk notification
   */
  sendBulkNotification(request: BulkNotificationRequest): Observable<any> {
    const formData = new FormData();
    
    // Add basic fields
    formData.append('name', request.name);
    formData.append('channel', request.channel);
    formData.append('message', request.message);
    
    if (request.subject) {
      formData.append('subject', request.subject);
    }
    
    if (request.scheduled_at) {
      formData.append('scheduled_at', request.scheduled_at);
    }

    if (request.metadata) {
      formData.append('metadata', JSON.stringify(request.metadata));
    }

    // Add recipients file or data
    if (request.recipients_file) {
      formData.append('recipients_file', request.recipients_file);
    } else if (request.recipients_data) {
      formData.append('recipients_data', JSON.stringify(request.recipients_data));
    }

    return this.apiService.post(`${this.baseEndpoint}/bulk/send/`, formData);
  }

  /**
   * Get notifications list
   */
  getNotifications(params?: { channel?: string; status?: string; page?: number }): Observable<ApiResponse<Notification>> {
    return this.apiService.get(`${this.baseEndpoint}/`, params);
  }

  /**
   * Get notification details
   */
  getNotification(id: string): Observable<Notification> {
    return this.apiService.get(`${this.baseEndpoint}/${id}/status/`);
  }

  /**
   * Cancel notification
   */
  cancelNotification(id: string): Observable<{ message: string; notification: Notification }> {
    return this.apiService.post(`${this.baseEndpoint}/${id}/cancel/`, {});
  }

  /**
   * Get bulk notifications
   */
  getBulkNotifications(): Observable<ApiResponse<any>> {
    return this.apiService.get(`${this.baseEndpoint}/bulk/`);
  }

  /**
   * Get bulk notification details
   */
  getBulkNotification(id: string): Observable<any> {
    return this.apiService.get(`${this.baseEndpoint}/bulk/${id}/`);
  }

  /**
   * Cancel bulk notification
   */
  cancelBulkNotification(id: string): Observable<{ message: string; bulk_notification: any }> {
    return this.apiService.post(`${this.baseEndpoint}/bulk/${id}/cancel/`, {});
  }

  /**
   * Get notification providers
   */
  getProviders(): Observable<Provider[]> {
    return this.apiService.get(`${this.baseEndpoint}/providers/`);
  }

  /**
   * Get dashboard statistics
   */
  getDashboardStats(): Observable<NotificationStats> {
    return this.apiService.get(`${this.baseEndpoint}/dashboard/stats/`);
  }

  /**
   * Get notification status options
   */
  getStatusOptions(): string[] {
    return ['pending', 'processing', 'sent', 'delivered', 'failed', 'cancelled'];
  }

  /**
   * Get channel options
   */
  getChannelOptions(): Array<{ value: string; label: string }> {
    return [
      { value: 'email', label: 'Email' },
      { value: 'sms', label: 'SMS' },
      { value: 'push', label: 'Push Notification' },
      { value: 'whatsapp', label: 'WhatsApp' }
    ];
  }

  /**
   * Get priority options
   */
  getPriorityOptions(): Array<{ value: string; label: string }> {
    return [
      { value: 'low', label: 'Low' },
      { value: 'normal', label: 'Normal' },
      { value: 'high', label: 'High' },
      { value: 'urgent', label: 'Urgent' }
    ];
  }

  /**
   * Validate recipient based on channel
   */
  validateRecipient(channel: string, recipient: string): boolean {
    switch (channel) {
      case 'email':
        return this.validateEmail(recipient);
      case 'sms':
      case 'whatsapp':
        return this.validatePhoneNumber(recipient);
      case 'push':
        return this.validateDeviceToken(recipient);
      default:
        return false;
    }
  }

  /**
   * Format recipient for display
   */
  formatRecipient(recipient: string, channel: string): string {
    switch (channel) {
      case 'sms':
      case 'whatsapp':
        return this.formatPhoneNumber(recipient);
      default:
        return recipient;
    }
  }

  /**
   * Get status badge class
   */
  getStatusBadgeClass(status: string): string {
    switch (status) {
      case 'pending':
        return 'badge-warning';
      case 'processing':
        return 'badge-info';
      case 'sent':
      case 'delivered':
        return 'badge-success';
      case 'failed':
        return 'badge-destructive';
      case 'cancelled':
        return 'badge-secondary';
      default:
        return 'badge-default';
    }
  }

  /**
   * Get channel icon
   */
  getChannelIcon(channel: string): string {
    switch (channel) {
      case 'email':
        return 'email';
      case 'sms':
        return 'sms';
      case 'push':
        return 'notifications';
      case 'whatsapp':
        return 'chat';
      default:
        return 'notification_important';
    }
  }

  /**
   * Estimate delivery time
   */
  estimateDeliveryTime(channel: string, priority: string): string {
    const baseTime = {
      'email': 2,
      'sms': 1,
      'push': 0.5,
      'whatsapp': 2
    };

    const priorityMultiplier = {
      'urgent': 0.5,
      'high': 0.75,
      'normal': 1.0,
      'low': 2.0
    };

    const base = baseTime[channel] || 2;
    const multiplier = priorityMultiplier[priority] || 1.0;
    const estimatedMinutes = base * multiplier;

    if (estimatedMinutes < 1) {
      return 'Less than 1 minute';
    } else if (estimatedMinutes < 60) {
      return `${Math.round(estimatedMinutes)} minutes`;
    } else {
      const hours = Math.round(estimatedMinutes / 60);
      return `${hours} hour${hours > 1 ? 's' : ''}`;
    }
  }

  // Private validation methods
  private validateEmail(email: string): boolean {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  private validatePhoneNumber(phone: string): boolean {
    const phoneRegex = /^\+?[1-9]\d{1,14}$/;
    return phoneRegex.test(phone.replace(/[\s-()]/g, ''));
  }

  private validateDeviceToken(token: string): boolean {
    // Basic validation for device tokens (should be non-empty and reasonably long)
    return token.length > 20;
  }

  private formatPhoneNumber(phone: string): string {
    // Remove all non-digit characters except +
    const cleaned = phone.replace(/[^\d+]/g, '');
    
    // Format based on length and presence of country code
    if (cleaned.startsWith('+')) {
      return cleaned;
    } else if (cleaned.length === 10) {
      // US number format
      return `+1${cleaned}`;
    } else {
      return `+${cleaned}`;
    }
  }
}
