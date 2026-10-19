export type LeafClass = "Healthy" | "Damaged";

export interface Detection {
  id: string;
  predicted_class: LeafClass;
  /** Probability (0..1) of the predicted class, as output by the model. */
  confidence: number;
  prob_healthy: number | null;
  prob_damaged: number | null;
  image_path: string | null;
  image_url: string | null;
  original_filename: string | null;
  model_version: string;
  created_at: string;
}

export interface PredictResponse extends Detection {
  low_confidence: boolean;
  warning: string | null;
  /** "leaf_regions" when the photo as a whole was not one leaf (e.g. a branch with fruit). */
  analysis: "whole_photo" | "leaf_regions";
  regions_used: number;
  regions_checked: number;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface StatBlock {
  total: number;
  period: number;
  previous_period: number;
  change_pct: number | null;
}

export interface Stats {
  days: number;
  total: StatBlock;
  healthy: StatBlock;
  damaged: StatBlock;
  latest: Detection | null;
}

export interface DailyPoint {
  date: string;
  Healthy: number;
  Damaged: number;
}

export interface Report {
  date_from: string;
  date_to: string;
  total: number;
  counts: Record<LeafClass, number>;
  average_confidence: Record<LeafClass, number | null>;
  low_confidence_count: number;
  daily: DailyPoint[];
}

export interface Health {
  status: "ok" | "degraded";
  app: string;
  model: { loaded: boolean; version: string | null; architecture: string | null; error: string | null };
  leaf_check: { loaded: boolean };
  database: { backend: string; connected: boolean; bucket?: string; error?: string; note?: string };
  image_retention: boolean;
  max_upload_mb: number;
  timezone: string;
}

export interface ClassMetrics {
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface SplitMetrics {
  n: number;
  accuracy: number;
  per_class: Record<LeafClass, ClassMetrics>;
  macro_f1: number;
  roc_auc?: number;
  confusion_matrix: number[][];
}

export interface ModelInfo {
  loaded: boolean;
  metadata: {
    architecture: string;
    model_version: string;
    trained_at: string;
    img_size: number;
    threshold: number;
    train_counts: Record<LeafClass, number>;
    validation: { loss: number; accuracy: number; auc: number };
    candidates: { arch: string; val_loss: number; val_accuracy: number; val_auc: number; epochs: number; params: number }[];
  } | null;
  evaluation: {
    evaluated_at: string;
    model_version: string;
    test: SplitMetrics;
    validation: SplitMetrics;
    train_no_augmentation: SplitMetrics;
    overfitting_check: { train_minus_test_accuracy: number; assessment: string };
    test_by_background: Record<string, SplitMetrics>;
    misclassified_test_count: number;
  } | null;
  leaf_check: {
    generated_at: string;
    calamansi_test_acceptance: Record<string, number>;
    negative_test_rejection: Record<string, { rejected: number; n: number }>;
    unseen_experiment?: {
      unseen_categories: string[];
      rejected_when_unseen: Record<string, { rejected: number; n: number }>;
    };
  } | null;
  dataset: {
    excluded_non_calamansi?: { count: number; reason: string };
    unique_source_photos: Record<LeafClass, number>;
    split_counts: Record<string, Record<LeafClass, number>>;
    split_strategy: string;
  } | null;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  username: string;
  role: "user" | "admin";
  account_status: "active" | "suspended";
  email_verified: boolean;
  /** Provisioned accounts must choose a new password before using the app. */
  must_change_password: boolean;
}

export interface AdminUser {
  id: string;
  email: string | null;
  full_name: string;
  username: string;
  role: "user" | "admin";
  account_status: "active" | "suspended";
  email_verified_at: string | null;
  created_at: string;
  updated_at: string | null;
  last_sign_in_at: string | null;
  must_change_password: boolean;
}

export interface AdminUserDetail extends AdminUser {
  detections: {
    total: number;
    healthy: number;
    damaged: number;
    recent: { id: string; predicted_class: LeafClass; confidence: number; created_at: string; original_filename: string | null }[];
  };
}

export interface ActivityEvent {
  id: number;
  event_type: string;
  event_status: "success" | "failure" | "blocked";
  user_id: string | null;
  user_name: string | null;
  created_at: string;
  details?: Record<string, unknown>;
}

export interface AdminOverview {
  days: number;
  users: {
    total: number;
    active: number;
    suspended: number;
    verified: number;
    unverified: number;
    admins: number;
    new_last_7_days: number;
    signed_in_last_7_days: number;
  };
  detections: { total: number; healthy: number; damaged: number; in_period: number };
  registrations_daily: { date: string; count: number }[];
  detections_daily: DailyPoint[];
  recent_registrations: AdminUser[];
  recent_activity: ActivityEvent[];
}
