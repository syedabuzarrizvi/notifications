import { Injectable } from '@angular/core';
import { HttpClient, HttpParams, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface ApiResponse<T> {
  count?: number;
  next?: string;
  previous?: string;
  results?: T[];
  data?: T;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
  ordering?: string;
  search?: string;
  [key: string]: any;
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private apiUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  /**
   * Generic GET request
   */
  get<T>(endpoint: string, params?: PaginationParams): Observable<T> {
    let httpParams = new HttpParams();
    
    if (params) {
      Object.keys(params).forEach(key => {
        const value = params[key];
        if (value !== null && value !== undefined && value !== '') {
          httpParams = httpParams.set(key, value.toString());
        }
      });
    }

    return this.http.get<T>(`${this.apiUrl}${endpoint}`, { params: httpParams });
  }

  /**
   * Generic POST request
   */
  post<T>(endpoint: string, data: any, options?: any): Observable<T> {
    return this.http.post<T>(`${this.apiUrl}${endpoint}`, data, options);
  }

  /**
   * Generic PUT request
   */
  put<T>(endpoint: string, data: any): Observable<T> {
    return this.http.put<T>(`${this.apiUrl}${endpoint}`, data);
  }

  /**
   * Generic PATCH request
   */
  patch<T>(endpoint: string, data: any): Observable<T> {
    return this.http.patch<T>(`${this.apiUrl}${endpoint}`, data);
  }

  /**
   * Generic DELETE request
   */
  delete<T>(endpoint: string): Observable<T> {
    return this.http.delete<T>(`${this.apiUrl}${endpoint}`);
  }

  /**
   * Upload file
   */
  uploadFile<T>(endpoint: string, file: File, additionalData?: any): Observable<T> {
    const formData = new FormData();
    formData.append('file', file);
    
    if (additionalData) {
      Object.keys(additionalData).forEach(key => {
        formData.append(key, additionalData[key]);
      });
    }

    return this.http.post<T>(`${this.apiUrl}${endpoint}`, formData);
  }

  /**
   * Download file
   */
  downloadFile(endpoint: string, filename?: string): Observable<Blob> {
    return this.http.get(`${this.apiUrl}${endpoint}`, {
      responseType: 'blob',
      headers: new HttpHeaders({
        'Accept': 'application/octet-stream'
      })
    });
  }

  /**
   * Build query parameters from object
   */
  buildParams(params: any): HttpParams {
    let httpParams = new HttpParams();
    
    Object.keys(params).forEach(key => {
      const value = params[key];
      if (value !== null && value !== undefined && value !== '') {
        if (Array.isArray(value)) {
          value.forEach(item => {
            httpParams = httpParams.append(key, item.toString());
          });
        } else {
          httpParams = httpParams.set(key, value.toString());
        }
      }
    });

    return httpParams;
  }

  /**
   * Handle file download with proper filename
   */
  downloadFileWithName(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  /**
   * Get full URL for endpoint
   */
  getFullUrl(endpoint: string): string {
    return `${this.apiUrl}${endpoint}`;
  }

  /**
   * Check if response has pagination
   */
  isPaginated<T>(response: any): response is ApiResponse<T> {
    return response && typeof response === 'object' && 'results' in response;
  }

  /**
   * Extract results from paginated response
   */
  extractResults<T>(response: ApiResponse<T> | T[]): T[] {
    if (this.isPaginated(response)) {
      return response.results || [];
    }
    return Array.isArray(response) ? response : [response];
  }

  /**
   * Get pagination info
   */
  getPaginationInfo<T>(response: ApiResponse<T>): {
    count: number;
    hasNext: boolean;
    hasPrevious: boolean;
    currentPage: number;
    totalPages: number;
  } | null {
    if (!this.isPaginated(response)) {
      return null;
    }

    const count = response.count || 0;
    const pageSize = 20; // Default page size
    const totalPages = Math.ceil(count / pageSize);
    
    // Extract page number from next/previous URLs
    let currentPage = 1;
    if (response.next) {
      const nextUrl = new URL(response.next);
      const nextPage = parseInt(nextUrl.searchParams.get('page') || '2');
      currentPage = nextPage - 1;
    } else if (response.previous) {
      const prevUrl = new URL(response.previous);
      const prevPage = parseInt(prevUrl.searchParams.get('page') || '1');
      currentPage = prevPage + 1;
    }

    return {
      count,
      hasNext: !!response.next,
      hasPrevious: !!response.previous,
      currentPage,
      totalPages
    };
  }

  /**
   * Format error message from API response
   */
  formatErrorMessage(error: any): string {
    if (typeof error === 'string') {
      return error;
    }

    if (error.error) {
      if (typeof error.error === 'string') {
        return error.error;
      }

      if (error.error.message) {
        return error.error.message;
      }

      if (error.error.detail) {
        return error.error.detail;
      }

      // Handle validation errors
      if (typeof error.error === 'object') {
        const messages: string[] = [];
        Object.keys(error.error).forEach(key => {
          const value = error.error[key];
          if (Array.isArray(value)) {
            messages.push(`${key}: ${value.join(', ')}`);
          } else {
            messages.push(`${key}: ${value}`);
          }
        });
        return messages.join('; ');
      }
    }

    if (error.message) {
      return error.message;
    }

    return 'An unknown error occurred';
  }

  /**
   * Retry failed requests
   */
  retryRequest<T>(request: Observable<T>, maxRetries: number = 3): Observable<T> {
    return request.pipe(
      // Add retry logic here if needed
    );
  }
}
