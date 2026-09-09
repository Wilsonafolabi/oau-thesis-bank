import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen08Saved = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Saved Research">
      <div className="mb-6 flex space-x-4 border-b border-slate-200">
        <button className="pb-3 border-b-2 border-[#00502F] text-[#00502F] font-medium text-sm">All Saved</button>
        <button className="pb-3 border-b-2 border-transparent text-slate-500 hover:text-slate-700 font-medium text-sm">Reading List</button>
        <button className="pb-3 border-b-2 border-transparent text-slate-500 hover:text-slate-700 font-medium text-sm">Literature Review</button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {MOCK_THESES.slice(1, 4).map(thesis => (
          <div key={thesis.id} className="relative group">
            <ThesisCard thesis={thesis} onClick={() => navigate('thesis-detail')} />
            <button className="absolute top-4 right-4 p-1.5 bg-white rounded-full shadow-sm text-red-500 opacity-0 group-hover:opacity-100 transition-opacity" title="Remove">
              <Bookmark className="w-4 h-4 fill-current" />
            </button>
          </div>
        ))}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen08Saved;
