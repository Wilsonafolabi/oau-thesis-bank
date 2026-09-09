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

const Screen33CollabOpportunity = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Opportunity Details">
      <div className="max-w-3xl mx-auto">
        <div className="mb-6 flex items-center cursor-pointer text-slate-500 hover:text-slate-800" onClick={() => navigate('collaboration-hub')}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to Hub
        </div>
        
        <Card className="p-8">
          <div className="flex items-center space-x-3 mb-4">
            <Badge variant="gold">Co-Author Needed</Badge>
            <span className="text-sm text-slate-500">Posted 2 days ago</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-4">Expanding NLP dataset for Yoruba Dialects</h1>
          
          <div className="flex items-center space-x-3 mb-8 p-4 bg-slate-50 rounded-lg border border-slate-100 cursor-pointer" onClick={() => navigate('researcher-profile')}>
            <div className="w-10 h-10 rounded-full bg-[#00502F] text-white flex items-center justify-center font-bold">EA</div>
            <div>
              <p className="text-sm font-semibold text-slate-900">Prof. E. R. Adagunodo</p>
              <p className="text-xs text-slate-500">Faculty • Computer Science</p>
            </div>
          </div>

          <div className="prose prose-slate max-w-none text-sm mb-8">
            <h3 className="text-lg font-semibold">Objective</h3>
            <p>We are extending a recent undergraduate thesis on Yoruba sentiment analysis to include specific regional dialects (Oyo, Ekiti, Ijebu). We are looking for a student or researcher with linguistics background to help annotate the new dataset.</p>
            
            <h3 className="text-lg font-semibold mt-6">Requirements</h3>
            <ul>
              <li>Fluency in at least two Yoruba dialects.</li>
              <li>Basic understanding of JSON/CSV data structures.</li>
              <li>Commitment of approx 5 hours/week for one month.</li>
            </ul>
          </div>

          <div className="flex space-x-4 pt-6 border-t border-slate-200">
            <Button onClick={() => navigate('messages')}>Apply / Message</Button>
            <Button variant="ghost"><Share2 className="w-4 h-4 mr-2"/> Share</Button>
          </div>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen33CollabOpportunity;
