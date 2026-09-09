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

const Screen37Notifications = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Notifications">
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="flex justify-between items-center mb-6">
          <div className="space-x-4">
            <button className="text-sm font-semibold text-[#00502F]">All</button>
            <button className="text-sm text-slate-500 hover:text-slate-700">Access Requests</button>
            <button className="text-sm text-slate-500 hover:text-slate-700">System</button>
          </div>
          <button className="text-sm text-slate-400 hover:text-slate-600">Mark all as read</button>
        </div>

        {[
          { icon: ShieldAlert, color: 'text-amber-500', bg: 'bg-amber-50', title: 'New Access Request', text: 'Tunde Bakare requested access to your embargoed thesis.', time: '2 hours ago', action: () => navigate('access-requests'), unread: true },
          { icon: CheckCircle, color: 'text-emerald-500', bg: 'bg-emerald-50', title: 'Processing Complete', text: 'AI processing for "Machine Learning for Crop Yield" is finished.', time: 'Yesterday', action: () => navigate('thesis-detail'), unread: false },
          { icon: MessageSquare, color: 'text-blue-500', bg: 'bg-blue-50', title: 'New Comment', text: 'Prof. Adagunodo commented on your methodology section.', time: '2 days ago', action: () => navigate('thesis-discussion'), unread: false }
        ].map((notif, i) => (
          <Card key={i} className={`p-4 flex items-start space-x-4 cursor-pointer transition-colors ${notif.unread ? 'bg-slate-50 border-l-4 border-l-[#00502F]' : 'hover:bg-slate-50'}`} onClick={notif.action}>
            <div className={`p-2 rounded-full ${notif.bg} ${notif.color}`}>
              <notif.icon className="w-5 h-5"/>
            </div>
            <div className="flex-1">
              <h4 className={`text-sm ${notif.unread ? 'font-bold text-slate-900' : 'font-medium text-slate-800'}`}>{notif.title}</h4>
              <p className="text-sm text-slate-600 mt-0.5">{notif.text}</p>
              <span className="text-xs text-slate-400 mt-2 block">{notif.time}</span>
            </div>
          </Card>
        ))}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen37Notifications;
