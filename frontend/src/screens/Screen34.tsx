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

const Screen34MentorshipRequest = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Request Mentorship">
      <div className="max-w-2xl mx-auto">
        <div className="mb-6 flex items-center cursor-pointer text-slate-500 hover:text-slate-800" onClick={() => navigate('researcher-profile')}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to Profile
        </div>
        
        <Card className="p-8">
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-full bg-[#00502F] text-white flex items-center justify-center font-bold text-xl mx-auto mb-3">AO</div>
            <h2 className="text-xl font-bold text-slate-900">Requesting mentorship from Adekunle Ojo</h2>
            <p className="text-sm text-slate-500 mt-1">Alumni • Agricultural Engineering</p>
          </div>

          <form className="space-y-6">
            <div className="flex flex-col space-y-1.5">
              <label className="text-sm font-medium text-slate-700">What do you need help with?</label>
              <select className="px-3 py-2 border border-slate-300 rounded-md bg-white text-sm">
                <option>Thesis Topic Selection</option>
                <option>Methodology Advice (Machine Learning)</option>
                <option>Career / Post-Grad Advice</option>
              </select>
            </div>
            
            <div className="flex flex-col space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Introduction & Goals</label>
              <textarea 
                className="px-3 py-2 border border-slate-300 rounded-md h-32 text-sm resize-none focus:ring-[#00502F] focus:border-[#00502F]" 
                placeholder="Briefly introduce yourself, your current project, and what specific guidance you are hoping to receive..."
              ></textarea>
            </div>

            <p className="text-xs text-slate-500 bg-slate-50 p-3 rounded">Note: Mentors are volunteers. Please be respectful of their time and ensure your request aligns with their listed research interests.</p>

            <Button className="w-full" onClick={() => { alert('Request sent! (Simulated)'); navigate('collaboration-hub'); }}>Send Request</Button>
          </form>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen34MentorshipRequest;
