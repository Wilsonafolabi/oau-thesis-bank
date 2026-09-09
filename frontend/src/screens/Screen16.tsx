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

const Screen16AccessPrivacy = () => {
  const { navigate } = useAppRouter();
  const options = [
    { id: 'public', title: 'Public Access', desc: 'Anyone can view and download the full document. Recommended for maximum impact.', icon: Unlock },
    { id: 'request', title: 'Request Access', desc: 'Metadata is public. Users must request permission to read the full text.', icon: ShieldAlert },
    { id: 'private', title: 'Private (Embargo)', desc: 'Hidden from public search. Only you and your supervisor can view it.', icon: Lock }
  ];

  return (
    <AuthenticatedLayout title="Access Settings">
      <div className="max-w-3xl mx-auto">
        <UploadWizardNav step={3} />
        <Card className="p-8">
          <h2 className="text-xl font-bold text-slate-900 mb-6">Who can view your research?</h2>
          <div className="space-y-4">
            {options.map(opt => (
              <div key={opt.id} className={`p-4 border-2 rounded-lg cursor-pointer flex items-start space-x-4 transition-colors ${opt.id === 'public' ? 'border-[#00502F] bg-emerald-50' : 'border-slate-200 hover:border-slate-300'}`}>
                <input type="radio" name="access" defaultChecked={opt.id === 'public'} className="mt-1 text-[#00502F] focus:ring-[#00502F]" />
                <div>
                  <h4 className="font-semibold text-slate-900 flex items-center"><opt.icon className="w-4 h-4 mr-2 text-slate-500"/> {opt.title}</h4>
                  <p className="text-sm text-slate-600 mt-1">{opt.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-8 mt-8 border-t border-slate-200 flex justify-between">
            <Button variant="ghost" onClick={() => navigate('thesis-metadata')}>Back</Button>
            <Button onClick={() => navigate('ai-processing')}>Begin Processing</Button>
          </div>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen16AccessPrivacy;
