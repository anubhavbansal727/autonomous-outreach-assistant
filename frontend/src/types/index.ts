export interface User {
  id: string
  email: string
  resend_domain: string | null
  created_at: string
}

export interface ProductProfile {
  id: string
  user_id: string
  source_url: string | null
  product_name: string
  one_liner: string | null
  target_customer: string | null
  pain_points: string[]
  differentiators: string[]
  case_studies: string[]
  cta: string | null
  icp: string | null
  avoid_messaging: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ScheduleOutput {
  send_at: string
  channel: 'email'
  recommended_window: string
  flag_for_human: boolean
  reason: string
}

export interface OutreachJob {
  id: string
  user_id: string
  product_profile_id: string | null
  company_name: string
  contact_name: string | null
  status: 'running' | 'done' | 'failed'
  current_step: 'researching' | 'personalizing' | 'scheduling' | 'complete' | null
  send_status: 'draft' | 'approved' | 'sent' | 'bounced' | 'replied'
  data_confidence: 'low' | 'medium' | 'high' | null
  email_subject: string | null
  email_draft: string | null
  linkedin_draft: string | null
  schedule_json: ScheduleOutput | null
  resend_message_id: string | null
  sent_at: string | null
  error_message: string | null
  retry_count: number
  token_usage: number | null
  created_at: string
  completed_at: string | null
}

export interface HistoryItem {
  id: string
  company_name: string
  contact_name: string | null
  status: string
  send_status: string
  data_confidence: string | null
  token_usage: number | null
  created_at: string
  sent_at: string | null
}

export interface JobStatusResponse {
  job_id: string
  status: 'running' | 'done' | 'failed'
  current_step: string | null
  created_at: string
}

export interface ApiError {
  error: string
  code: string
  retry_after?: number
}

export interface IngestionResultResponse {
  job_id: string
  status: 'running' | 'done' | 'failed'
  current_step: string | null
  profile: Record<string, unknown> | null
  error_message: string | null
}
