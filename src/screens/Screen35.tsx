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

const Screen35Messages = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Messages">
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex h-[75vh] overflow-hidden">
        {/* List */}
        <div className="w-full md:w-1/3 border-r border-slate-200 flex flex-col">
          <div className="p-4 border-b border-slate-200">
            <input type="text" placeholder="Search messages..." className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-md text-sm outline-none" />
          </div>
          <div className="flex-1 overflow-y-auto">
            {MOCK_MESSAGES.map((msg, i) => (
              <div key={msg.id} className={`p-4 border-b border-slate-100 cursor-pointer hover:bg-slate-50 ${i===0 ? 'bg-emerald-50/50' : ''}`} onClick={() => navigate('conversation')}>
                <div className="flex justify-between items-baseline mb-1">
                  <h4 className={`text-sm font-semibold text-slate-900 ${msg.unread ? 'text-[#00502F]' : ''}`}>{msg.sender}</h4>
                  <span className="text-xs text-slate-500">{msg.time}</span>
                </div>
                <p className={`text-sm truncate ${msg.unread ? 'text-slate-800 font-medium' : 'text-slate-500'}`}>{msg.text}</p>
              </div>
            ))}
          </div>
        </div>
        
        {/* Placeholder for Desktop */}
        <div className="hidden md:flex flex-1 items-center justify-center bg-slate-50 text-slate-400 flex-col">
          <MessageSquare className="w-12 h-12 mb-4 opacity-50"/>
          <p>Select a conversation to start messaging</p>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen35Messages;
