/** 通用分页响应 */
export interface PaginatedResponse<T> {
  items: T[];
  total_count: number;
  page: number;
  page_size: number;
}

/** 同步日志条目（SyncLogs 完整版 + Dashboard 子集均可使用） */
export interface SyncLogItem {
  id: number;
  sync_task_id: number | null;
  connector_id: number;
  entity: string;
  direction: string;
  status: string;
  total_records: number;
  success_count: number;
  failure_count: number;
  error_details: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
}
