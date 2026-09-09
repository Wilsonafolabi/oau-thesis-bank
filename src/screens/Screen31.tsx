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

const Screen31ResearcherActivity = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Research Timeline: Adekunle Ojo">
      <div className="max-w-3xl mx-auto">
        <div className="mb-8 flex items-center cursor-pointer text-slate-500 hover:text-slate-800" onClick={() => navigate('researcher-profile')}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to Profile
        </div>

        <div className="relative border-l-2 border-slate-200 ml-3 md:ml-6 space-y-12 pb-12">
          {/* Timeline Item 1 */}
          <div className="relative pl-8 md:pl-10">
            <div className="absolute left-[-9px] top-1 w-4 h-4 rounded-full bg-[#00502F] ring-4 ring-white"></div>
            <span className="text-sm font-bold text-[#D4AF37] mb-1 block">Oct 2023</span>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Published Undergraduate Thesis</h3>
            <Card className="p-4 cursor-pointer hover:border-[#00502F]" onClick={() => navigate('thesis-detail')}>
              <h4 className="font-semibold text-slate-800">Machine Learning for Crop Yield Prediction in Nigeria</h4>
              <p className="text-sm text-slate-500 mt-1">Supervised by Dr. O. A. Fajemisin</p>
            </Card>
          </div>

          {/* Timeline Item 2 */}
          <div className="relative pl-8 md:pl-10">
            <div className="absolute left-[-9px] top-1 w-4 h-4 rounded-full bg-slate-300 ring-4 ring-white"></div>
            <span className="text-sm font-bold text-slate-500 mb-1 block">Jun 2023</span>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Dataset Published</h3>
            <Card className="p-4 bg-slate-50">
              <div className="flex items-center text-sm font-medium text-slate-700">
                <Database className="w-4 h-4 mr-2 text-slate-400"/> 
                <span>Osun State 10-Year Agricultural Dataset</span>
              </div>
            </Card>
          </div>

           {/* Timeline Item 3 */}
           <div className="relative pl-8 md:pl-10">
            <div className="absolute left-[-9px] top-1 w-4 h-4 rounded-full bg-slate-300 ring-4 ring-white"></div>
            <span className="text-sm font-bold text-slate-500 mb-1 block">Feb 2023</span>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Proposal Defended</h3>
            <p className="text-sm text-slate-600">Department of Agricultural Engineering, Obafemi Awolowo University.</p>
          </div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen31ResearcherActivity;
