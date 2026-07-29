import type { GameState } from "@/lib/engine/reducer";
import type { FeedEntry } from "@/lib/game/types";

/**
 * Hand-written schema types for the tables this app touches.
 *
 * Supabase can generate these, but generation needs a live project and a CLI
 * login — which would make a typecheck depend on the network. Written by hand,
 * the compiler catches a column typo the same way, and `0001_init.sql` stays the
 * single source of truth that both this file and the database follow.
 */

type Timestamp = string;

export interface Database {
  public: {
    Tables: {
      profiles: {
        Row: {
          id: string;
          display_name: string;
          avatar_seed: string;
          created_at: Timestamp;
        };
        Insert: {
          id: string;
          display_name?: string;
          avatar_seed?: string;
        };
        Update: Partial<{ display_name: string; avatar_seed: string }>;
        Relationships: [];
      };

      games: {
        Row: {
          id: string;
          room_code: string;
          case_id: string;
          host_id: string;
          status: "lobby" | "active" | "finished";
          state: GameState;
          state_version: number;
          max_players: number;
          created_at: Timestamp;
          started_at: Timestamp | null;
          finished_at: Timestamp | null;
        };
        Insert: {
          id?: string;
          room_code: string;
          case_id: string;
          host_id: string;
          status?: "lobby" | "active" | "finished";
          state: GameState;
          state_version?: number;
          max_players?: number;
        };
        Update: Partial<{
          status: "lobby" | "active" | "finished";
          state: GameState;
          state_version: number;
          started_at: Timestamp;
          finished_at: Timestamp;
        }>;
        Relationships: [];
      };

      game_players: {
        Row: {
          game_id: string;
          user_id: string;
          display_name: string;
          is_host: boolean;
          joined_at: Timestamp;
          last_seen_at: Timestamp;
        };
        Insert: {
          game_id: string;
          user_id: string;
          display_name: string;
          is_host?: boolean;
        };
        Update: Partial<{ display_name: string; last_seen_at: Timestamp }>;
        Relationships: [];
      };

      game_events: {
        Row: {
          id: number;
          game_id: string;
          seq: number;
          actor_id: string | null;
          type: string;
          payload: Omit<FeedEntry, "seq">;
          created_at: Timestamp;
        };
        Insert: {
          game_id: string;
          seq: number;
          actor_id?: string | null;
          type: string;
          payload: Omit<FeedEntry, "seq">;
        };
        Update: never;
        Relationships: [];
      };

      chat_messages: {
        Row: {
          id: number;
          game_id: string;
          user_id: string;
          body: string;
          created_at: Timestamp;
        };
        Insert: { game_id: string; user_id: string; body: string };
        Update: never;
        Relationships: [];
      };

      board_cards: {
        Row: {
          game_id: string;
          clue_id: string;
          x: number;
          y: number;
          updated_at: Timestamp;
          updated_by: string | null;
        };
        Insert: {
          game_id: string;
          clue_id: string;
          x: number;
          y: number;
          updated_by?: string | null;
        };
        Update: Partial<{ x: number; y: number }>;
        Relationships: [];
      };

      board_links: {
        Row: {
          id: string;
          game_id: string;
          from_clue_id: string;
          to_clue_id: string;
          label: string;
          created_by: string | null;
          created_at: Timestamp;
        };
        Insert: {
          id?: string;
          game_id: string;
          from_clue_id: string;
          to_clue_id: string;
          label?: string;
          created_by?: string | null;
        };
        Update: never;
        Relationships: [];
      };

      board_notes: {
        Row: {
          id: string;
          game_id: string;
          x: number;
          y: number;
          body: string;
          created_by: string | null;
          created_at: Timestamp;
        };
        Insert: {
          id?: string;
          game_id: string;
          x: number;
          y: number;
          body?: string;
          created_by?: string | null;
        };
        Update: Partial<{ x: number; y: number; body: string }>;
        Relationships: [];
      };
    };
    Views: Record<never, never>;
    Functions: {
      is_member: {
        Args: { target_game: string };
        Returns: boolean;
      };
    };
    Enums: Record<never, never>;
    CompositeTypes: Record<never, never>;
  };
}
