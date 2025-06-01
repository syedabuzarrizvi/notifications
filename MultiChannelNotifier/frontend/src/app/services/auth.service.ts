import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { map, catchError, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { User } from '../shared/models/user.model';

interface AuthResponse {
  message: string;
  merchant: User;
  tokens: {
    access: string;
    refresh: string;
  };
}

interface LoginCredentials {
  username: string;
  password: string;
}

interface RegisterData {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name: string;
  last_name: string;
  company_name: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = environment.apiUrl;
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  private isAuthenticatedSubject = new BehaviorSubject<boolean>(false);

  public currentUser$ = this.currentUserSubject.asObservable();
  public isAuthenticated$ = this.isAuthenticatedSubject.asObservable();

  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    this.checkAuthStatus();
  }

  /**
   * Check current authentication status
   */
  checkAuthStatus(): void {
    const token = this.getAccessToken();
    const user = this.getCurrentUser();
    
    if (token && user) {
      this.currentUserSubject.next(user);
      this.isAuthenticatedSubject.next(true);
    } else {
      this.clearTokens();
      this.isAuthenticatedSubject.next(false);
    }
  }

  /**
   * Login user
   */
  login(credentials: LoginCredentials): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.apiUrl}/auth/login/`, credentials)
      .pipe(
        tap(response => {
          this.setTokens(response.tokens.access, response.tokens.refresh);
          this.setCurrentUser(response.merchant);
          this.currentUserSubject.next(response.merchant);
          this.isAuthenticatedSubject.next(true);
        })
      );
  }

  /**
   * Register new user
   */
  register(userData: RegisterData): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.apiUrl}/auth/register/`, userData)
      .pipe(
        tap(response => {
          this.setTokens(response.tokens.access, response.tokens.refresh);
          this.setCurrentUser(response.merchant);
          this.currentUserSubject.next(response.merchant);
          this.isAuthenticatedSubject.next(true);
        })
      );
  }

  /**
   * Logout user
   */
  logout(): Observable<any> {
    const refreshToken = this.getRefreshToken();
    
    if (refreshToken) {
      return this.http.post(`${this.apiUrl}/auth/logout/`, { refresh: refreshToken })
        .pipe(
          catchError(() => of(null)), // Ignore logout errors
          tap(() => {
            this.clearTokens();
            this.currentUserSubject.next(null);
            this.isAuthenticatedSubject.next(false);
          })
        );
    }

    this.clearTokens();
    this.currentUserSubject.next(null);
    this.isAuthenticatedSubject.next(false);
    return of(null);
  }

  /**
   * Refresh access token
   */
  refreshToken(): Observable<{ access: string }> {
    const refreshToken = this.getRefreshToken();
    
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    return this.http.post<{ access: string }>(`${this.apiUrl}/auth/token/refresh/`, {
      refresh: refreshToken
    }).pipe(
      tap(response => {
        this.setAccessToken(response.access);
      }),
      catchError(error => {
        this.clearTokens();
        this.isAuthenticatedSubject.next(false);
        this.router.navigate(['/login']);
        throw error;
      })
    );
  }

  /**
   * Get current user profile
   */
  getProfile(): Observable<User> {
    return this.http.get<User>(`${this.apiUrl}/auth/profile/`);
  }

  /**
   * Update user profile
   */
  updateProfile(userData: Partial<User>): Observable<User> {
    return this.http.patch<User>(`${this.apiUrl}/auth/profile/`, userData)
      .pipe(
        tap(user => {
          this.setCurrentUser(user);
          this.currentUserSubject.next(user);
        })
      );
  }

  /**
   * Get user settings
   */
  getSettings(): Observable<any> {
    return this.http.get(`${this.apiUrl}/auth/settings/`);
  }

  /**
   * Update user settings
   */
  updateSettings(settings: any): Observable<any> {
    return this.http.patch(`${this.apiUrl}/auth/settings/`, settings);
  }

  /**
   * Get API key
   */
  getApiKey(): Observable<{ api_key: string; usage_info: any }> {
    return this.http.get<{ api_key: string; usage_info: any }>(`${this.apiUrl}/auth/api-key/`);
  }

  /**
   * Regenerate API key
   */
  regenerateApiKey(): Observable<{ message: string; api_key: string }> {
    return this.http.post<{ message: string; api_key: string }>(`${this.apiUrl}/auth/api-key/regenerate/`, {});
  }

  // Token management
  private setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
  }

  private setAccessToken(accessToken: string): void {
    localStorage.setItem('access_token', accessToken);
  }

  getAccessToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token');
  }

  clearTokens(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
  }

  // User management
  private setCurrentUser(user: User): void {
    localStorage.setItem('current_user', JSON.stringify(user));
  }

  getCurrentUser(): User | null {
    const userStr = localStorage.getItem('current_user');
    return userStr ? JSON.parse(userStr) : null;
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    const token = this.getAccessToken();
    if (!token) {
      return false;
    }

    // Check if token is expired (basic check)
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const expiry = payload.exp * 1000; // Convert to milliseconds
      return Date.now() < expiry;
    } catch {
      return false;
    }
  }

  /**
   * Get current user value
   */
  get currentUserValue(): User | null {
    return this.currentUserSubject.value;
  }

  /**
   * Get authentication status
   */
  get isAuthenticatedValue(): boolean {
    return this.isAuthenticatedSubject.value;
  }
}
